"""The HTTP layer. A thin wrapper around the pipeline and the job registry."""

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import Annotated

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from book2audio.models import parse_page_spec
from book2audio.pipeline import EXTRACTORS, destination
from book2audio.preflight import INSTALL, NotEnoughSpace, check_space, missing_tools
from book2audio.script_check import language_warning
from book2audio.tts.base import DEFAULTS
from book2audio.tts.cache import SynthCache
from book2audio.web.jobs import JobStore, State
from book2audio.web.paths import BadDestination, resolve_destination, suggestions
from book2audio.web.runner import Runner, build_engine

STATIC = Path(__file__).parent / "static"

SUPPORTED_LANGUAGES = {"ru", "en"}
SUPPORTED_GENDERS = {"male", "female"}

# How many characters of prose make one second of audio. Measured on real books.
CHARS_PER_SECOND = 15.0

# The phrase for the voice sample. The Russian one holds the homograph «замок»:
# on it you hear whether the engine places the stress itself. Both are long enough
# to judge a voice at x2 and short enough to synthesize instantly.
SAMPLE_TEXT = {
    "ru": "Замок на двери был старше самого дома, и открыть его удавалось не с первого раза.",
    "en": "The lock on the door was older than the house itself, and it never opened first try.",
}

# The pause between state polls for the progress stream.
POLL_SECONDS = 0.4

# The lifetime limit of one SSE connection. The browser reconnects on its own,
# while an endless connection holds a thread even after the tab is closed.
STREAM_MAX_SECONDS = 300.0


async def progress_events(
    store: JobStore,
    job_id: str,
    poll_seconds: float = POLL_SECONDS,
    max_seconds: float = STREAM_MAX_SECONDS,
):
    """Streams the job state while it changes. One direction only."""
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
    copy_to: Path | None = None,
) -> FastAPI:
    # Starting through uvicorn goes by the import string and an argument cannot
    # reach it, so the path arrives from the environment.
    copy_to = copy_to or destination(None)
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
        cache_root=root / "cache",
    )

    app = FastAPI(title="book2audio", docs_url=None, redoc_url=None)
    app.state.store = store
    app.state.runner = runner

    def require(job_id: str):
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.get("/health")
    def health() -> dict:
        # The book language is not known here, so we ask about every tool.
        absent = missing_tools()
        return {
            "status": "degraded" if absent else "ok",
            "missing": absent,
            "install": [INSTALL[tool] for tool in absent],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/settings")
    def settings() -> dict:
        """Where the finished book goes. The interface shows the real path."""
        return {
            "destination": str(copy_to) if copy_to else None,
            "suggestions": suggestions(),
        }

    @app.get("/api/voices")
    def voices(language: str = "ru") -> dict:
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"language {language} is not supported")
        engine = build_engine(language, engine_name)
        defaults = {gender: DEFAULTS.get((language, gender)) for gender in SUPPORTED_GENDERS}
        return {
            "engine": engine.name,
            "defaults": defaults,
            "voices": [{"id": v.id, "gender": v.gender} for v in engine.voices()],
        }

    @app.get("/api/sample")
    def sample(language: str = "ru", voice: str = ""):
        """One phrase in the chosen voice. A narrator has to be heard, not read."""
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"language {language} is not supported")
        engine = build_engine(language, engine_name)
        known = {v.id for v in engine.voices()}
        if voice not in known:
            raise HTTPException(status_code=400, detail=f"unknown voice: {voice}")

        # The cache works like the one for books but sits apart: samples outlive
        # the jobs being deleted.
        cache = SynthCache(root / "samples")
        path = cache.synth(engine, SAMPLE_TEXT[language], voice)
        return FileResponse(path, media_type="audio/wav", filename=f"{voice}.wav")

    @app.post("/api/jobs", status_code=201)
    async def create_job(
        file: Annotated[UploadFile, File()],
        language: Annotated[str, Form()] = "ru",
        gender: Annotated[str, Form()] = "female",
        pages: Annotated[str, Form()] = "",
    ) -> dict:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in EXTRACTORS:
            known = ", ".join(sorted(EXTRACTORS))
            raise HTTPException(
                status_code=400, detail=f"format {suffix} is not supported, I can do: {known}"
            )
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=400, detail=f"language {language} is not supported")
        if gender not in SUPPORTED_GENDERS:
            raise HTTPException(status_code=400, detail=f"gender {gender} is not supported")

        # Only PDF has pages. EPUB and FB2 do not, and quietly pretending they do
        # means lying about how much work there is.
        if pages.strip() and suffix != ".pdf":
            raise HTTPException(
                status_code=400, detail=f"{suffix} has no pages, pick chapters after parsing"
            )
        try:
            parse_page_spec(pages)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        target = uploads / f"{Path(file.filename).stem[:60]}{suffix}"
        stored = target
        counter = 1
        while stored.exists():
            stored = target.with_stem(f"{target.stem}-{counter}")
            counter += 1
        with stored.open("wb") as handle:
            shutil.copyfileobj(file.file, handle)

        job = store.create(source=stored, language=language, gender=gender, selection=pages.strip())
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
            raise HTTPException(status_code=409, detail="the book is still being parsed")
        chars = sum(len(c["text"]) for c in chapters if c.get("include", True))
        minutes = chars / CHARS_PER_SECOND / 60
        engine = build_engine(job.language, engine_name)
        text = " ".join(c["text"] for c in chapters if c.get("include", True))
        return {
            "title": job.title,
            "chapters": chapters,
            "chars": chars,
            "minutes": round(minutes, 1),
            # How long the wait is. With Kokoro it is six times longer than with
            # Silero, and you want to know that before pressing the button.
            "synth_minutes": round(minutes / engine.realtime, 1),
            "warning": language_warning(text, job.language),
        }

    @app.get("/api/jobs/{job_id}/report")
    def report(job_id: str) -> dict:
        """What cleaning dropped and what failed to synthesize."""
        job = require(job_id)
        work = root / "work" / job.id

        def load(name: str) -> dict | None:
            path = work / name
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))

        return {"clean": load("clean_report.json"), "synth": load("synth_report.json")}

    @app.put("/api/jobs/{job_id}/review")
    def put_review(job_id: str, payload: Annotated[dict, Body()]) -> dict:
        require(job_id)
        chapters = payload.get("chapters")
        if not isinstance(chapters, list):
            raise HTTPException(status_code=400, detail="a list of chapters was expected")
        store.save_review(job_id, chapters)
        return {"ok": True}

    @app.post("/api/jobs/{job_id}/synthesize", status_code=202)
    def synthesize(job_id: str, payload: Annotated[dict | None, Body()] = None) -> dict:
        payload = payload or {}
        job = require(job_id)
        # FAILED is here on purpose: a failed job can be restarted, the synthesis
        # cache is shared, so a retry costs only the assembly.
        if job.state not in {State.READY, State.UPLOADED, State.EXTRACTING, State.FAILED}:
            raise HTTPException(status_code=409, detail=f"the job is in state {job.state.value}")

        # The intermediate wavs take an order of magnitude more room than the
        # finished m4b. Learning that mid-book means losing the whole run.
        chapters = store.get_review(job_id) or []
        chars = sum(len(c["text"]) for c in chapters if c.get("include", True))
        try:
            check_space(root / "work", chars)
        except NotEnoughSpace as exc:
            raise HTTPException(status_code=507, detail=str(exc)) from exc
        try:
            chosen = resolve_destination(payload.get("destination"))
        except BadDestination as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        store.set_options(
            job_id,
            voice=payload.get("voice") or "",
            selection=job.selection or "",
            audio_format=payload.get("format", "m4b"),
            destination=str(chosen) if chosen else None,
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
            raise HTTPException(status_code=409, detail="the book is not ready yet")
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
