"""HTTP-слой. Тонкая обёртка над конвейером и реестром задач."""

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from book2audio.pipeline import EXTRACTORS, ICLOUD_AUDIOBOOKS
from book2audio.preflight import INSTALL, NotEnoughSpace, check_space, missing_tools
from book2audio.tts.base import DEFAULTS
from book2audio.web.jobs import JobStore, State
from book2audio.web.runner import Runner, build_engine

STATIC = Path(__file__).parent / "static"

SUPPORTED_LANGUAGES = {"ru", "en"}
SUPPORTED_GENDERS = {"male", "female"}

# Сколько символов проза даёт в секунду озвучки. Замер на реальных книгах.
CHARS_PER_SECOND = 15.0

# Пауза между опросами состояния для потока прогресса.
POLL_SECONDS = 0.4

# Предел жизни одного SSE-соединения. Браузер переподключается сам, а вечное
# соединение держит поток даже после того, как вкладку закрыли.
STREAM_MAX_SECONDS = 300.0


async def progress_events(
    store: JobStore,
    job_id: str,
    poll_seconds: float = POLL_SECONDS,
    max_seconds: float = STREAM_MAX_SECONDS,
):
    """Отдаёт состояние задачи, пока оно меняется. Поток в одну сторону."""
    previous = None
    deadline = time.monotonic() + max_seconds
    while time.monotonic() < deadline:
        job = store.get(job_id)
        if job is None:
            break
        payload = job.as_dict()
        if payload != previous:
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            previous = payload
        if job.state in {State.DONE, State.FAILED, State.CANCELLED}:
            break
        await asyncio.sleep(poll_seconds)


def create_app(
    root: Path | None = None,
    engine_name: str = "",
    copy_to: Path | None = ICLOUD_AUDIOBOOKS,
) -> FastAPI:
    root = Path(root or Path.home() / ".book2audio")
    uploads = root / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)

    store = JobStore(root / "jobs.db")
    runner = Runner(
        store,
        work_root=root / "work",
        out_root=root / "output",
        engine_name=engine_name,
        copy_to=copy_to,
    )

    app = FastAPI(title="book2audio", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.runner = runner

    def require(job_id: str):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="задача не найдена")
        return job

    @app.get("/health")
    def health() -> dict:
        # Языка книги здесь ещё нет, поэтому спрашиваем обо всех инструментах.
        absent = missing_tools()
        return {
            "status": "degraded" if absent else "ok",
            "missing": absent,
            "install": [INSTALL[tool] for tool in absent],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/voices")
    def voices(language: str = "ru") -> dict:
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"язык {language} не поддерживается")
        engine = build_engine(language, engine_name)
        defaults = {gender: DEFAULTS.get((language, gender)) for gender in SUPPORTED_GENDERS}
        return {
            "engine": engine.name,
            "defaults": defaults,
            "voices": [{"id": v.id, "gender": v.gender} for v in engine.voices()],
        }

    @app.post("/api/jobs", status_code=201)
    async def create_job(
        file: Annotated[UploadFile, File()],
        language: Annotated[str, Form()] = "ru",
        gender: Annotated[str, Form()] = "female",
    ) -> dict:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in EXTRACTORS:
            known = ", ".join(sorted(EXTRACTORS))
            raise HTTPException(
                status_code=400, detail=f"формат {suffix} не поддерживается, умею: {known}"
            )
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"язык {language} не поддерживается")
        if gender not in SUPPORTED_GENDERS:
            raise HTTPException(status_code=400, detail=f"пол {gender} не поддерживается")

        target = uploads / f"{Path(file.filename).stem[:60]}{suffix}"
        stored = target
        counter = 1
        while stored.exists():
            stored = target.with_stem(f"{target.stem}-{counter}")
            counter += 1
        with stored.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        job = store.create(source=stored, language=language, gender=gender)
        runner.start_extraction(job.id)
        return {"id": job.id}

    @app.get("/api/jobs")
    def list_jobs() -> dict:
        return {"jobs": [job.as_dict() for job in store.recent()]}

    @app.get("/api/jobs/{job_id}")
    def job_state(job_id: str) -> dict:
        return require(job_id).as_dict()

    @app.get("/api/jobs/{job_id}/review")
    def get_review(job_id: str) -> dict:
        job = require(job_id)
        chapters = store.get_review(job.id)
        if chapters is None:
            raise HTTPException(status_code=409, detail="книга ещё разбирается")
        chars = sum(len(c["text"]) for c in chapters if c.get("include", True))
        return {
            "title": job.title,
            "chapters": chapters,
            "chars": chars,
            "minutes": round(chars / CHARS_PER_SECOND / 60, 1),
        }

    @app.put("/api/jobs/{job_id}/review")
    def put_review(job_id: str, payload: Annotated[dict, Body()]) -> dict:
        require(job_id)
        chapters = payload.get("chapters")
        if not isinstance(chapters, list):
            raise HTTPException(status_code=400, detail="ожидался список глав")
        store.save_review(job_id, chapters)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/synthesize", status_code=202)
    def synthesize(job_id: str, payload: Annotated[dict | None, Body()] = None) -> dict:
        payload = payload or {}
        job = require(job_id)
        if job.state not in {State.READY, State.UPLOADED, State.EXTRACTING}:
            raise HTTPException(status_code=409, detail=f"задача в состоянии {job.state.value}")

        # Промежуточные wav занимают на порядок больше готового m4b. Узнать
        # об этом на середине книги значит потерять весь прогон.
        chapters = store.get_review(job_id) or []
        chars = sum(len(c["text"]) for c in chapters if c.get("include", True))
        try:
            check_space(root / "work", chars)
        except NotEnoughSpace as exc:
            raise HTTPException(status_code=507, detail=str(exc)) from exc
        store.set_options(
            job_id,
            voice=payload.get("voice") or "",
            selection="",
            audio_format=payload.get("format", "m4b"),
        )
        runner.enqueue(job_id)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict:
        require(job_id)
        try:
            store.cancel(job_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/download")
    def download(job_id: str):
        job = require(job_id)
        if job.state != State.DONE or not job.result:
            raise HTTPException(status_code=409, detail="книга ещё не готова")
        if job.result.is_dir():
            archive = Path(shutil.make_archive(str(job.result), "zip", job.result))
            return FileResponse(archive, filename=archive.name)
        return FileResponse(job.result, filename=job.result.name)

    @app.delete("/api/jobs/{job_id}")
    def delete_job(job_id: str) -> dict:
        job = require(job_id)
        shutil.rmtree(root / "work" / job.id, ignore_errors=True)
        shutil.rmtree(root / "output" / job.id, ignore_errors=True)
        with store._connect() as db:
            db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return {"ok": True}

    @app.get("/api/jobs/{job_id}/events")
    async def events(job_id: str):
        require(job_id)
        return StreamingResponse(
            progress_events(store, job_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if STATIC.exists():
        app.mount("/static", StaticFiles(directory=STATIC), name="static")

    return app


app = create_app()
