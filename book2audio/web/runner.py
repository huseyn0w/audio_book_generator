"""Фоновый исполнитель задач.

Один поток на всё: пользователь один, задача одна. Отдельный процесс-воркер
и брокер здесь не окупаются, а состояние в SQLite позволяет перезапустить
веб-процесс, не потеряв задачу.
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
from book2audio.models import Block, Chapter, Document, parse_page_spec
from book2audio.pipeline import ICLOUD_AUDIOBOOKS, pick_extractor
from book2audio.tts.base import TTSEngine, pick_default
from book2audio.tts.cache import SynthCache
from book2audio.tts.fake import FakeEngine
from book2audio.tts.kokoro import KokoroEngine
from book2audio.tts.silero import SileroEngine
from book2audio.web.jobs import Job, JobStore, State


class Cancelled(Exception):
    """Задачу отменили из интерфейса."""


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
        copy_to: Path | None = ICLOUD_AUDIOBOOKS,
    ) -> None:
        self.store = store
        self.work_root = Path(work_root)
        self.out_root = Path(out_root)
        self.engine_name = engine_name
        self.copy_to = copy_to
        # Один рабочий поток: синтез упирается в CPU, параллелить нечего.
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="book2audio")
        self._engines: dict[str, TTSEngine] = {}

    def stop(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)

    def _engine_for(self, language: str) -> TTSEngine:
        """Движок кэшируется: загрузка весов Silero занимает секунды."""
        if language not in self._engines:
            self._engines[language] = build_engine(language, self.engine_name)
        return self._engines[language]

    # --- извлечение ---

    def start_extraction(self, job_id: str) -> None:
        self.pool.submit(self._guarded, job_id, self._extract)

    def _extract(self, job: Job) -> None:
        self.store.set_state(job.id, State.EXTRACTING)
        work = self.work_root / job.id
        work.mkdir(parents=True, exist_ok=True)
        extractor = pick_extractor(job.source, clean=True, language=job.language)
        document = extractor.extract(job.source, parse_page_spec(job.selection))

        # Через браузер не видно, что именно чистка выбросила. Отчёт кладём
        # рядом с отчётом о синтезе, отдаётся отдельным роутом.
        report = getattr(extractor, "report", None)
        if report is not None:
            (work / "clean_report.json").write_text(
                json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        self.store.set_title(job.id, document.title)
        # Синтез пересобирает документ из правленого текста, обложка туда
        # не попадает. Кладём её на диск сейчас, пока она ещё в руках.
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

    # --- синтез ---

    def enqueue(self, job_id: str) -> None:
        self.store.mark_queued(job_id)
        self.pool.submit(self._guarded, job_id, self._synthesize)

    def _document_from_review(self, job: Job) -> Document:
        """Собирает документ из правленого текста, а не из исходника заново."""
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
        """Голос, который движок действительно умеет.

        Значения по умолчанию заданы для Silero и Kokoro, но движок может
        быть другим, а сохранённый голос устареть после смены модели.
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
            raise ValueError("нечего озвучивать: не выбрано ни одной главы")

        engine = self._engine_for(job.language)
        voice = self.voice_for(engine, job)

        grouped = [
            chunk_document(
                Document(document.title, None, document.language, [chapter]), job.language
            )
            for chapter in document.chapters
        ]
        total = sum(len(g) for g in grouped)
        self.store.set_progress(job.id, "synth", 0, total)

        work = self.work_root / job.id
        work.mkdir(parents=True, exist_ok=True)
        cache = SynthCache(work / "cache")
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
                ChapterAudio(chapter.title or f"Глава {index + 1}", joined, wav_duration(joined))
            )

        # Сорванные чанки стали тишиной. Отчёт лежит рядом с отчётом о чистке.
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

        if self.copy_to and result.is_file():
            # Папка в iCloud Drive: файл сам приезжает в Файлы на iPhone.
            self.copy_to.mkdir(parents=True, exist_ok=True)
            shutil.copy2(result, self.copy_to / result.name)

        self.store.finish(job.id, result)

    # --- общая обвязка ---

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
        except Exception as exc:  # noqa: BLE001 — задача не должна ронять поток
            self.store.fail(job_id, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
