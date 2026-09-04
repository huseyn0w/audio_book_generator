"""Оркестрация конвейера: книга на входе, wav на выходе.

Движок передаётся аргументом, поэтому тесты гоняют весь конвейер
с заглушкой за секунды. Реальный движок выбирает CLI.
"""

import json
import re
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
from book2audio.models import Document, Selection
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

# Куда класть готовую книгу, чтобы она сама приехала в Файлы на iPhone.
ICLOUD_AUDIOBOOKS = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs/Audiobooks"


def pick_extractor(path: Path, clean: bool) -> Extractor:
    factory = EXTRACTORS.get(path.suffix.lower())
    if factory is None:
        known = ", ".join(sorted(EXTRACTORS))
        raise ValueError(f"неизвестный формат {path.suffix!r}, умею пока: {known}")
    return factory(clean=clean)


def _safe_name(title: str) -> str:
    """Имя файла из названия книги. Слеши и двоеточия ломают путь."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", title)
    cleaned = " ".join(cleaned.split())
    return cleaned[:120] or "book"


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
    """Гонит книгу через весь конвейер и отдаёт путь к готовому wav."""
    path = Path(path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work_dir = Path(work_dir) if work_dir else out_dir / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)

    known_voices = {v.id for v in engine.voices()}
    if voice not in known_voices:
        raise ValueError(f"неизвестный голос {voice!r} для движка {engine.name}")

    def report(stage: Stage, done: int, total: int) -> None:
        if on_progress:
            on_progress(Progress(stage=stage, done=done, total=total))

    report("extract", 0, 1)
    extractor = pick_extractor(path, clean)
    document = extractor.extract(path, selection)
    clean_report = getattr(extractor, "report", None)
    if clean_report is not None:
        (work_dir / "clean_report.json").write_text(
            json.dumps(clean_report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    report("extract", 1, 1)

    report("chunk", 0, 1)
    grouped: list[list[Chunk]] = [
        chunk_document(
            Document(document.title, document.author, document.language, [chapter]), language
        )
        for chapter in document.chapters
    ]
    total = sum(len(g) for g in grouped)
    if not total:
        raise ValueError("в выбранном диапазоне нет текста")
    report("chunk", 1, 1)

    cache = SynthCache(work_dir / "cache")
    pauses = work_dir / "pauses"
    pauses.mkdir(exist_ok=True)

    def gap_for(seconds: float) -> Path:
        path = pauses / f"{seconds:.3f}_{engine.sample_rate}.wav"
        if not path.exists():
            silence(path, seconds, engine.sample_rate)
        return path

    # Чанки помнят, из какой главы пришли: без этого не собрать оглавление m4b.
    done = 0
    chapter_parts: list[list[Path]] = []
    for chunks_of_chapter in grouped:
        parts: list[Path] = []
        for chunk in chunks_of_chapter:
            parts.append(cache.synth(engine, chunk.text, voice))
            if chunk.pause_after > 0:
                parts.append(gap_for(chunk.pause_after))
            done += 1
            report("synth", done, total)
        chapter_parts.append(parts)

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
            ChapterAudio(chapter.title or f"Глава {index + 1}", joined, wav_duration(joined))
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
