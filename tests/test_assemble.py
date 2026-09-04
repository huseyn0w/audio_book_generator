import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from book2audio.assemble import (
    ChapterAudio,
    build_chapter_metadata,
    write_m4b,
    write_mp3_per_chapter,
)
from book2audio.audio import write_wav_mono16
from book2audio.models import Document


def make_wav(path: Path, seconds: float, rate: int = 24000) -> Path:
    write_wav_mono16(path, np.zeros(int(rate * seconds), dtype=np.float32), rate)
    return path


def sample_doc():
    return Document(title="Тестовая книга", author="Автор", language="ru", chapters=[])


# --- метаданные глав ---


def test_metadata_starts_with_the_ffmpeg_header():
    meta = build_chapter_metadata([ChapterAudio("Глава раз", Path("a.wav"), 10.0)], sample_doc())
    assert meta.startswith(";FFMETADATA1")


def test_metadata_carries_title_and_author():
    meta = build_chapter_metadata([ChapterAudio("Гл", Path("a.wav"), 5.0)], sample_doc())
    assert "title=Тестовая книга" in meta
    assert "artist=Автор" in meta


def test_metadata_uses_milliseconds_and_consecutive_ranges():
    chapters = [
        ChapterAudio("Раз", Path("a.wav"), 10.0),
        ChapterAudio("Два", Path("b.wav"), 5.5),
    ]
    meta = build_chapter_metadata(chapters, sample_doc())
    assert "TIMEBASE=1/1000" in meta
    assert "START=0" in meta
    assert "END=10000" in meta
    assert "START=10000" in meta
    assert "END=15500" in meta


def test_metadata_escapes_special_characters_in_titles():
    """Знак равенства и точка с запятой в названии ломают формат ffmetadata."""
    meta = build_chapter_metadata(
        [ChapterAudio("Глава = раз; и два", Path("a.wav"), 1.0)], sample_doc()
    )
    assert r"\=" in meta
    assert r"\;" in meta


def test_metadata_handles_an_empty_chapter_list():
    meta = build_chapter_metadata([], sample_doc())
    assert meta.startswith(";FFMETADATA1")
    assert "[CHAPTER]" not in meta


# --- m4b ---


def test_m4b_is_produced_and_playable(tmp_path):
    parts = [
        ChapterAudio("Первая", make_wav(tmp_path / "a.wav", 1.0), 1.0),
        ChapterAudio("Вторая", make_wav(tmp_path / "b.wav", 1.0), 1.0),
    ]
    out = write_m4b(parts, sample_doc(), tmp_path / "book.m4b")
    assert out.exists()
    assert out.suffix == ".m4b"
    assert out.stat().st_size > 500


def test_m4b_contains_the_chapters(tmp_path):
    parts = [
        ChapterAudio("Первая", make_wav(tmp_path / "a.wav", 1.0), 1.0),
        ChapterAudio("Вторая", make_wav(tmp_path / "b.wav", 1.0), 1.0),
    ]
    out = write_m4b(parts, sample_doc(), tmp_path / "book.m4b")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "default=nw=1", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.count("TAG:title=") == 2
    assert "TAG:title=Первая" in probe.stdout
    assert "TAG:title=Вторая" in probe.stdout
    assert "start_time=1.000000" in probe.stdout


def test_m4b_carries_book_metadata(tmp_path):
    parts = [ChapterAudio("Гл", make_wav(tmp_path / "a.wav", 1.0), 1.0)]
    out = write_m4b(parts, sample_doc(), tmp_path / "book.m4b")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-of", "default=nw=1", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Тестовая книга" in probe.stdout


def test_m4b_embeds_a_cover_when_given(tmp_path):
    cover = tmp_path / "cover.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=gray:s=64x64",
            "-frames:v",
            "1",
            str(cover),
        ],
        check=True,
        capture_output=True,
    )
    parts = [ChapterAudio("Гл", make_wav(tmp_path / "a.wav", 1.0), 1.0)]
    out = write_m4b(parts, sample_doc(), tmp_path / "book.m4b", cover=cover)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "default=nw=1", str(out)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "codec_type=video" in probe.stdout


def test_m4b_refuses_an_empty_chapter_list(tmp_path):
    with pytest.raises(ValueError, match="нечего собирать"):
        write_m4b([], sample_doc(), tmp_path / "book.m4b")


# --- mp3 по главам ---


def test_mp3_writes_one_numbered_file_per_chapter(tmp_path):
    parts = [
        ChapterAudio("Первая", make_wav(tmp_path / "a.wav", 1.0), 1.0),
        ChapterAudio("Вторая глава", make_wav(tmp_path / "b.wav", 1.0), 1.0),
    ]
    folder = write_mp3_per_chapter(parts, sample_doc(), tmp_path / "out")
    files = sorted(p.name for p in folder.glob("*.mp3"))
    assert files == ["01 Первая.mp3", "02 Вторая глава.mp3"]


def test_mp3_files_are_playable(tmp_path):
    parts = [ChapterAudio("Гл", make_wav(tmp_path / "a.wav", 1.0), 1.0)]
    folder = write_mp3_per_chapter(parts, sample_doc(), tmp_path / "out")
    mp3 = next(folder.glob("*.mp3"))
    duration = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert float(duration.stdout) == pytest.approx(1.0, abs=0.2)


def test_mp3_sanitizes_names_that_break_paths(tmp_path):
    parts = [ChapterAudio("Гл/ава: раз", make_wav(tmp_path / "a.wav", 1.0), 1.0)]
    folder = write_mp3_per_chapter(parts, sample_doc(), tmp_path / "out")
    name = next(folder.glob("*.mp3")).name
    assert "/" not in name.replace("01 ", "")
    assert ":" not in name


def test_wav_duration_helper_matches_the_file(tmp_path):
    from book2audio.assemble import wav_duration

    path = make_wav(tmp_path / "a.wav", 2.5)
    assert wav_duration(path) == pytest.approx(2.5, abs=0.01)
    with wave.open(str(path)) as w:
        assert w.getnframes() == 60000
