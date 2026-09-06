"""Pipeline orchestration: a book in, a wav out.

The engine arrives as an argument, so the tests run the whole pipeline with a
stub in seconds. The CLI picks the real engine.
"""

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from book2audio.assemble import ChapterAudio, wav_duration, write_m4b, write_mp3_per_chapter
from book2audio.audio import concat, silence
from book2audio.chunker import Chunk, chunk_document
from book2audio.extract.base import Extractor
from book2audio.extract.epub import EpubExtractor
from book2audio.extract.fb2 import Fb2Extractor
from book2audio.extract.pdf import PdfExtractor
from book2audio.models import CHAPTER_LABEL, Document, Selection
from book2audio.tts.base import TTSEngine
from book2audio.tts.cache import SynthCache

Stage = str


@dataclass(frozen=True)
class Progress:
    stage: Stage
    done: int
    total: int


ProgressHook = Callable[[Progress], None]

EXTRACTORS: dict[str, Callable[..., Extractor]] = {
    ".pdf": PdfExtractor,
    ".epub": EpubExtractor,
    ".fb2": Fb2Extractor,
}

# The environment variable for the web process: uvicorn with --reload builds the
# app itself from the import string, and an argument cannot reach it.
COPY_TO_ENV = "BOOK2AUDIO_COPY_TO"


def destination(explicit: Path | None) -> Path | None:
    """Where to copy the finished book.

    An explicit path wins over the environment. Without either, no copy is made:
    the book is taken with the Download button from a phone or a computer.
    """
    if explicit is not None:
        return Path(explicit).expanduser()
    from os import environ

    value = environ.get(COPY_TO_ENV, "").strip()
    return Path(value).expanduser() if value else None


def pick_extractor(path: Path, clean: bool, language: str = "ru") -> Extractor:
    factory = EXTRACTORS.get(path.suffix.lower())
    if factory is None:
        known = ", ".join(sorted(EXTRACTORS))
        raise ValueError(f"unknown format {path.suffix!r}, so far I can do: {known}")
    return factory(clean=clean, language=language)


def _safe_name(title: str) -> str:
    """A file name from the book title. Slashes and colons break the path."""
    from book2audio.assemble import safe_filename

    return safe_filename(title, limit=120)


def _write_cover(work_dir: Path, data: bytes) -> Path:
    """Puts the image on disk: ffmpeg takes the cover as a file, not as bytes."""
    target = work_dir / "cover.jpg"
    target.write_bytes(data)
    return target


def convert(
    path: Path,
    language: str,
    voice: str,
    out_dir: Path,
    engine: TTSEngine,
    selection: Selection | None = None,
    work_dir: Path | None = None,
    on_progress: ProgressHook | None = None,
    clean: bool = True,
    audio_format: str = "m4b",
    cover: Path | None = None,
    copy_to: Path | None = None,
) -> Path:
    """Runs the book through the whole pipeline and returns the path to the wav."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir) if work_dir else out_dir / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)

    known_voices = {v.id for v in engine.voices()}
    if voice not in known_voices:
        raise ValueError(f"unknown voice {voice!r} for engine {engine.name}")

    def report(stage: Stage, done: int, total: int) -> None:
        if on_progress:
            on_progress(Progress(stage=stage, done=done, total=total))

    report("extract", 0, 1)
    extractor = pick_extractor(path, clean, language)
    document = extractor.extract(path, selection)
    clean_report = getattr(extractor, "report", None)
    if clean_report is not None:
        (work_dir / "clean_report.json").write_text(
            json.dumps(clean_report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if cover is None and document.cover:
        cover = _write_cover(work_dir, document.cover)
    report("extract", 1, 1)

    report("chunk", 0, 1)
    grouped: list[list[Chunk]] = [
        chunk_document(
            Document(document.title, document.author, document.language, [chapter]),
            language,
            limit=engine.max_chars,
        )
        for chapter in document.chapters
    ]
    total = sum(len(g) for g in grouped)
    if not total:
        raise ValueError("the chosen range holds no text")
    report("chunk", 1, 1)

    cache = SynthCache(work_dir / "cache")
    pauses = work_dir / "pauses"
    pauses.mkdir(exist_ok=True)

    def gap_for(seconds: float) -> Path:
        path = pauses / f"{seconds:.3f}_{engine.sample_rate}.wav"
        if not path.exists():
            silence(path, seconds, engine.sample_rate)
        return path

    # Chunks remember the chapter they came from: without it the m4b table of
    # contents cannot be built.
    done = 0
    chapter_parts: list[list[Path]] = []
    for chunks_of_chapter in grouped:
        parts: list[Path] = []
        for chunk in chunks_of_chapter:
            parts.append(cache.synth_or_silence(engine, chunk.text, voice))
            if chunk.pause_after > 0:
                parts.append(gap_for(chunk.pause_after))
            done += 1
            report("synth", done, total)
        chapter_parts.append(parts)

    # The report is written only when there is something to say: an empty file
    # next to the book teaches you not to look at it.
    if cache.failures:
        (work_dir / "synth_report.json").write_text(
            json.dumps(cache.report(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    report("assemble", 0, 1)
    chapters_dir = work_dir / "chapters"
    chapters_dir.mkdir(exist_ok=True)

    built: list[ChapterAudio] = []
    for index, (chapter, parts) in enumerate(zip(document.chapters, chapter_parts, strict=True)):
        if not parts:
            continue
        joined = chapters_dir / f"{index:04d}.wav"
        concat(parts, joined, engine.sample_rate)
        built.append(
            ChapterAudio(
                chapter.title or f"{CHAPTER_LABEL[language]} {index + 1}",
                joined,
                wav_duration(joined),
            )
        )

    name = _safe_name(document.title)
    if audio_format == "mp3":
        target = write_mp3_per_chapter(built, document, out_dir / name)
    else:
        target = write_m4b(built, document, out_dir / f"{name}.m4b", cover=cover)
    report("assemble", 1, 1)

    if copy_to:
        copy_to.mkdir(parents=True, exist_ok=True)
        if target.is_dir():
            shutil.copytree(target, copy_to / target.name, dirs_exist_ok=True)
        else:
            shutil.copy2(target, copy_to / target.name)

    return target
