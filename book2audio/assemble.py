"""Сборка готовой аудиокниги.

m4b это стандарт аудиокниг: один файл, главы внутри, обложка, а плеер
запоминает позицию. Именно поэтому он основной формат выдачи, а mp3
по главам остаётся опцией.
"""

import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from book2audio.audio import concat
from book2audio.models import Document

BITRATE = "64k"

# Символы, ломающие формат ffmetadata: знак равенства и точка с запятой
# разделяют поля, обратный слэш экранирует.
FFMETADATA_SPECIAL = re.compile(r"([=;#\\\n])")

FILENAME_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass(frozen=True)
class ChapterAudio:
    title: str
    path: Path
    seconds: float


def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def _escape(value: str) -> str:
    return FFMETADATA_SPECIAL.sub(r"\\\1", value)


def safe_filename(name: str, limit: int = 90) -> str:
    cleaned = " ".join(FILENAME_UNSAFE.sub(" ", name).split())
    return cleaned[:limit] or "chapter"


def build_chapter_metadata(chapters: list[ChapterAudio], document: Document) -> str:
    """Файл ;FFMETADATA1 с блоками [CHAPTER]. Время в миллисекундах."""
    lines = [";FFMETADATA1", f"title={_escape(document.title)}"]
    if document.author:
        lines.append(f"artist={_escape(document.author)}")
    lines.append("genre=Audiobook")

    start_ms = 0
    for chapter in chapters:
        end_ms = start_ms + round(chapter.seconds * 1000)
        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={_escape(chapter.title)}",
        ]
        start_ms = end_ms
    return "\n".join(lines) + "\n"


def write_m4b(
    chapters: list[ChapterAudio],
    document: Document,
    target: Path,
    cover: Path | None = None,
) -> Path:
    """Склеивает главы в m4b с оглавлением, метаданными и обложкой."""
    if not chapters:
        raise ValueError("нечего собирать: список глав пуст")

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as workspace:
        work = Path(workspace)
        joined = work / "joined.wav"
        concat([c.path for c in chapters], joined, _sample_rate(chapters[0].path))

        meta = work / "chapters.txt"
        meta.write_text(build_chapter_metadata(chapters, document), encoding="utf-8")

        command = ["ffmpeg", "-y", "-v", "error", "-i", str(joined), "-i", str(meta)]
        if cover:
            command += ["-i", str(cover)]
        command += ["-map", "0:a", "-map_metadata", "1"]
        if cover:
            command += ["-map", "2:v", "-c:v", "mjpeg", "-disposition:v", "attached_pic"]
        command += ["-c:a", "aac", "-b:a", BITRATE, "-ac", "1", "-f", "mp4", str(target)]
        subprocess.run(command, check=True, capture_output=True)
    return target


def write_mp3_per_chapter(chapters: list[ChapterAudio], document: Document, folder: Path) -> Path:
    """Папка с пронумерованными mp3 и тегами. Опция для плееров без m4b."""
    folder.mkdir(parents=True, exist_ok=True)
    for number, chapter in enumerate(chapters, start=1):
        target = folder / f"{number:02d} {safe_filename(chapter.title)}.mp3"
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(chapter.path),
            "-c:a",
            "libmp3lame",
            "-b:a",
            BITRATE,
            "-ac",
            "1",
            "-metadata",
            f"title={chapter.title}",
            "-metadata",
            f"album={document.title}",
            "-metadata",
            f"track={number}",
        ]
        if document.author:
            command += ["-metadata", f"artist={document.author}"]
        command.append(str(target))
        subprocess.run(command, check=True, capture_output=True)
    return folder


def _sample_rate(path: Path) -> int:
    with wave.open(str(path)) as handle:
        return handle.getframerate()
