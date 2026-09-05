"""Запись и преобразование wav. Всё моно, 16 бит."""

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SAMPLE_WIDTH = 2

# Сколько последних строк stderr класть в ошибку. ffmpeg печатает сотни
# строк о потоках и кодеках, причина падения всегда в конце.
STDERR_LINES = 20


class FfmpegError(subprocess.CalledProcessError):
    """Падение ffmpeg вместе с причиной.

    Раньше наверх шёл голый CalledProcessError: код возврата и командная
    строка, без stderr. Сборка книги на 13 часов упала с «exit status 255»,
    и по этому сообщению нельзя было понять, что ffmpeg убили сигналом.
    """

    @staticmethod
    def tail(text: str) -> str:
        return "\n".join(text.strip().splitlines()[-STDERR_LINES:])

    @staticmethod
    def explain(code: int) -> str:
        """Расшифровка кода возврата, если он значит что-то известное."""
        if code < 0:
            return f"код {code}: процесс убит сигналом {-code}"
        if code == 255:
            return (
                "код 255: ffmpeg получил сигнал и прервался (обычно SIGTERM при остановке сервера)"
            )
        return f"код {code}"

    def __str__(self) -> str:
        parts = [f"ffmpeg не справился, {self.explain(self.returncode)}"]
        stderr = self.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        if stderr and stderr.strip():
            parts.append(self.tail(stderr))
        return "\n".join(parts)


def run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess:
    """Запускает ffmpeg и отдаёт понятную ошибку вместо голого кода возврата."""
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise FfmpegError(done.returncode, command, done.stdout, done.stderr)
    return done


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
    run_ffmpeg(["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={factor}", str(dst)])


def concat(parts: list[Path], dst: Path, sample_rate: int) -> None:
    """Склеивает wav-файлы в один.

    Список путей идёт через временный файл, а не через аргументы: книга даёт
    тысячи чанков, и командная строка такой список не вместит.
    """
    if not parts:
        raise ValueError("нечего склеивать: пустой список файлов")

    # Демуксер concat пропускает несуществующий файл и выходит с нулём:
    # книга молча теряет кусок. Проверяем сами, до запуска.
    missing = [str(p) for p in parts if not p.exists()]
    if missing:
        raise FileNotFoundError(f"нет файлов для склейки: {', '.join(missing[:5])}")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as listing:
        for part in parts:
            escaped = str(part.resolve()).replace("'", r"'\''")
            listing.write(f"file '{escaped}'\n")
        listing_path = Path(listing.name)

    try:
        run_ffmpeg(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing_path),
                "-ar",
                str(sample_rate),
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(dst),
            ]
        )
    finally:
        listing_path.unlink(missing_ok=True)
