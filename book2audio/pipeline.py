"""Оркестрация конвейера: книга на входе, wav на выходе.

Движок передаётся аргументом, поэтому тесты гоняют весь конвейер
с заглушкой за секунды. Реальный движок выбирает CLI.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from book2audio.audio import concat, silence
from book2audio.chunker import chunk_document
from book2audio.extract.base import Extractor
from book2audio.extract.pdf import PdfExtractor
from book2audio.models import Selection
from book2audio.tts.base import TTSEngine
from book2audio.tts.cache import SynthCache

Stage = str


@dataclass(frozen=True)
class Progress:
    stage: Stage
    done: int
    total: int


ProgressHook = Callable[[Progress], None]

EXTRACTORS: dict[str, Callable[..., Extractor]] = {".pdf": PdfExtractor}


def _pick_extractor(path: Path, clean: bool) -> Extractor:
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
    extractor = _pick_extractor(path, clean)
    document = extractor.extract(path, selection)
    clean_report = getattr(extractor, "report", None)
    if clean_report is not None:
        (work_dir / "clean_report.json").write_text(
            json.dumps(clean_report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    report("extract", 1, 1)

    report("chunk", 0, 1)
    chunks = chunk_document(document, language)
    if not chunks:
        raise ValueError("в выбранном диапазоне нет текста")
    report("chunk", 1, 1)

    cache = SynthCache(work_dir / "cache")
    pauses = work_dir / "pauses"
    pauses.mkdir(exist_ok=True)

    parts: list[Path] = []
    for index, chunk in enumerate(chunks, start=1):
        parts.append(cache.synth(engine, chunk.text, voice))
        if chunk.pause_after > 0:
            gap = pauses / f"{chunk.pause_after:.3f}_{engine.sample_rate}.wav"
            if not gap.exists():
                silence(gap, chunk.pause_after, engine.sample_rate)
            parts.append(gap)
        report("synth", index, len(chunks))

    report("assemble", 0, 1)
    target = out_dir / f"{_safe_name(document.title)}.wav"
    concat(parts, target, engine.sample_rate)
    report("assemble", 1, 1)

    return target
