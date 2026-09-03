"""Запись и преобразование wav. Всё моно, 16 бит."""

import subprocess
import wave
from pathlib import Path

import numpy as np

SAMPLE_WIDTH = 2


def write_wav_mono16(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """Пишет float-семплы из диапазона [-1, 1] в wav. Выход за диапазон обрезается."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def silence(path: Path, seconds: float, sample_rate: int) -> None:
    """Пишет wav с тишиной заданной длины."""
    frames = round(seconds * sample_rate)
    write_wav_mono16(path, np.zeros(frames, dtype=np.float32), sample_rate)


def change_speed(src: Path, dst: Path, factor: float) -> None:
    """Меняет темп без изменения высоты тона. atempo держит диапазон 0.5-100."""
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={factor}", str(dst)],
        check=True,
        capture_output=True,
    )
