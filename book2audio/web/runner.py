"""The background job runner.

One thread for everything: one user, one job. A separate worker process and a
broker do not pay for themselves here, and state in SQLite lets the web process
restart without losing the job.
"""

import json
import shutil
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from book2audio.assemble import (
    ChapterAudio,
    safe_filename,
    wav_duration,
    write_m4b,
    write_mp3_per_chapter,
)
from book2audio.audio import concat, silence
from book2audio.chunker import chunk_document
from book2audio.extract.base import NoTextLayer
from book2audio.models import (
    CHAPTER_LABEL,
    Block,
    Chapter,
    Document,
    parse_page_spec,
)
from book2audio.pipeline import pick_extractor
from book2audio.tts.base import TTSEngine, pick_default
from book2audio.tts.cache import SynthCache
from book2audio.tts.fake import FakeEngine
from book2audio.tts.kokoro import KokoroEngine
from book2audio.tts.silero import SileroEngine
from book2audio.web.jobs import Job, JobStore, State


class Cancelled(Exception):
    """The job was cancelled from the interface."""


def build_engine(language: str, engine_name: str = "") -> TTSEngine:
    if engine_name == "fake":
        return FakeEngine()
    return SileroEngine() if language == "ru" else KokoroEngine()


class Runner:
    def __init__(
        self,
        store: JobStore,
        work_root: Path,
        out_root: Path,
        engine_name: str = "",
        copy_to: Path | None = None,
        cache_root: Path | None = None,
    ) -> None:
        self.store = store
        self.work_root = Path(work_root)
        self.out_root = Path(out_root)
        # The cache is shared by every job and sits outside work: the key comes from
        # the text, the voice and the engine version, and the job has nothing to do
        # with it. It used to live inside work/<job_id>, and uploading a book again
        # recomputed everything.
        self.cache_root = Path(cache_root) if cache_root else self.work_root.parent / "cache"
        self.engine_name = engine_name
        self.copy_to = copy_to
        # One worker thread: synthesis is CPU bound, there is nothing to parallelize.
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="book2audio")
        self._engines: dict[str, TTSEngine] = {}

    def stop(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _engine_for(self, language: str) -> TTSEngine:
        """The engine is cached: loading the Silero weights takes seconds."""
        if language not in self._engines:
            self._engines[language] = build_engine(language, self.engine_name)
        return self._engines[language]

    # --- extraction ---

    def start_extraction(self, job_id: str) -> None:
        self.pool.submit(self._guarded, job_id, self._extract)

    def _extract(self, job: Job) -> None:
        self.store.set_state(job.id, State.EXTRACTING)
        work = self.work_root / job.id
        work.mkdir(parents=True, exist_ok=True)
        extractor = pick_extractor(job.source, clean=True, language=job.language)
        document = extractor.extract(job.source, parse_page_spec(job.selection))

        # From the browser you cannot see what cleaning dropped. The report goes
        # next to the synthesis report and is served by its own route.
        report = getattr(extractor, "report", None)
        if report is not None:
            (work / "clean_report.json").write_text(
                json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        self.store.set_title(job.id, document.title)
        # Synthesis rebuilds the document from the edited text, and the cover does
        # not travel with it. We put it on disk now, while we still hold it.
        if document.cover:
            (work / "cover.jpg").write_bytes(document.cover)
        self.store.save_review(
            job.id,
            [
                {
                    "title": chapter.title,
                    "text": "\n\n".join(b.text for b in chapter.blocks),
                    "include": True,
                }
                for chapter in document.chapters
            ],
        )
        self.store.set_state(job.id, State.READY)

    # --- synthesis ---

    def enqueue(self, job_id: str) -> None:
        self.store.mark_queued(job_id)
        self.pool.submit(self._guarded, job_id, self._synthesize)

    def _document_from_review(self, job: Job) -> Document:
        """Builds the document from the edited text, not from the source again."""
        review = self.store.get_review(job.id) or []
        chapters = [
            Chapter(
                title=entry["title"],
                blocks=[
                    Block(kind="paragraph", text=paragraph.strip())
                    for paragraph in entry["text"].split("\n\n")
                    if paragraph.strip()
                ],
            )
            for entry in review
            if entry.get("include", True) and entry.get("text", "").strip()
        ]
        return Document(
            title=job.title or job.source.stem,
            author=None,
            language=job.language,
            chapters=chapters,
        )

    def voice_for(self, engine: TTSEngine, job: Job) -> str:
        """A voice the engine actually has.

        The defaults are set for Silero and Kokoro, but the engine may be another
        one, and a saved voice can go stale after a model change.
        """
        available = {v.id: v.gender for v in engine.voices()}
        if job.voice and job.voice in available:
            return job.voice
        default = pick_default(job.language, job.gender) if job.gender else None
        if default in available:
            return default
        same_gender = [vid for vid, gender in available.items() if gender == job.gender]
        return same_gender[0] if same_gender else next(iter(available))

    def _synthesize(self, job: Job) -> None:
        self.store.set_state(job.id, State.SYNTHESIZING)
        document = self._document_from_review(job)
        if not document.chapters:
            raise ValueError("nothing to read: no chapter was selected")

        engine = self._engine_for(job.language)
        voice = self.voice_for(engine, job)

        grouped = [
            chunk_document(
                Document(document.title, None, document.language, [chapter]),
                job.language,
                limit=engine.max_chars,
            )
            for chapter in document.chapters
        ]
        total = sum(len(g) for g in grouped)
        self.store.set_progress(job.id, "synth", 0, total)

        work = self.work_root / job.id
        work.mkdir(parents=True, exist_ok=True)
        cache = SynthCache(self.cache_root)
        pauses = work / "pauses"
        pauses.mkdir(exist_ok=True)
        chapters_dir = work / "chapters"
        chapters_dir.mkdir(exist_ok=True)

        def gap(seconds: float) -> Path:
            path = pauses / f"{seconds:.3f}_{engine.sample_rate}.wav"
            if not path.exists():
                silence(path, seconds, engine.sample_rate)
            return path

        done = 0
        built: list[ChapterAudio] = []
        for index, (chapter, chunks) in enumerate(zip(document.chapters, grouped, strict=True)):
            parts: list[Path] = []
            for chunk in chunks:
                if self.store.is_cancelled(job.id):
                    raise Cancelled
                parts.append(cache.synth_or_silence(engine, chunk.text, voice))
                if chunk.pause_after > 0:
                    parts.append(gap(chunk.pause_after))
                done += 1
                self.store.set_progress(job.id, "synth", done, total)
            if not parts:
                continue
            joined = chapters_dir / f"{index:04d}.wav"
            concat(parts, joined, engine.sample_rate)
            built.append(
                ChapterAudio(
                    chapter.title or f"{CHAPTER_LABEL[job.language]} {index + 1}",
                    joined,
                    wav_duration(joined),
                )
            )

        # Failed chunks became silence. The report sits next to the cleaning report.
        if cache.failures:
            (work / "synth_report.json").write_text(
                json.dumps(cache.report(), ensure_ascii=False, indent=2), encoding="utf-8"
            )

        self.store.set_progress(job.id, "assemble", total, total)
        out_dir = self.out_root / job.id
        name = safe_filename(document.title)
        if job.audio_format == "mp3":
            result = write_mp3_per_chapter(built, document, out_dir / name)
        else:
            cover = work / "cover.jpg"
            result = write_m4b(
                built, document, out_dir / f"{name}.m4b", cover=cover if cover.exists() else None
            )

        # The folder chosen for this book wins over the one the server started with.
        folder = Path(job.destination) if job.destination else self.copy_to
        if folder and result.is_file():
            folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result, folder / result.name)

        self.store.finish(job.id, result)

    # --- the shared wiring ---

    def _guarded(self, job_id: str, action) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        try:
            action(job)
        except Cancelled:
            pass
        except NoTextLayer as exc:
            self.store.fail(job_id, str(exc))
        except Exception as exc:  # noqa: BLE001 - a job must not kill the thread
            # Silero throws a bare ValueError with no text, and the failure screen
            # was left with an empty line. The class name is always there.
            detail = str(exc).strip() or "no details, look at the server log"
            self.store.fail(job_id, f"{type(exc).__name__}: {detail}")
            traceback.print_exc()
