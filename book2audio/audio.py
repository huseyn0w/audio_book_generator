"""Writing and converting wav. Everything is mono, 16 bit."""

import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SAMPLE_WIDTH = 2

# How many trailing stderr lines go into the error. ffmpeg prints hundreds of
# lines about streams and codecs, and the cause is always at the end.
STDERR_LINES = 20


class FfmpegError(subprocess.CalledProcessError):
    """An ffmpeg failure together with its cause.

    A bare CalledProcessError used to travel up: the return code and the command
    line, without stderr. A 13 hour book build died with "exit status 255", and
    that message gave no way to tell that ffmpeg had been killed by a signal.
    """

    @staticmethod
    def tail(text: str) -> str:
        return "\n".join(text.strip().splitlines()[-STDERR_LINES:])

    @staticmethod
    def explain(code: int) -> str:
        """What the return code means, when it means something known."""
        if code < 0:
            return f"code {code}: the process was killed by signal {-code}"
        if code == 255:
            return "code 255: ffmpeg got a signal and stopped (usually SIGTERM on server shutdown)"
        return f"code {code}"

    def __str__(self) -> str:
        parts = [f"ffmpeg failed, {self.explain(self.returncode)}"]
        stderr = self.stderr
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        if stderr and stderr.strip():
            parts.append(self.tail(stderr))
        return "\n".join(parts)


def run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess:
    """Runs ffmpeg and gives a readable error instead of a bare return code."""
    done = subprocess.run(command, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise FfmpegError(done.returncode, command, done.stdout, done.stderr)
    return done


def write_wav_mono16(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    """Writes float samples from [-1, 1] into a wav. Values outside are clipped."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(SAMPLE_WIDTH)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())


def silence(path: Path, seconds: float, sample_rate: int) -> None:
    """Writes a wav of silence of the given length."""
    frames = round(seconds * sample_rate)
    write_wav_mono16(path, np.zeros(frames, dtype=np.float32), sample_rate)


def change_speed(src: Path, dst: Path, factor: float) -> None:
    """Changes tempo without changing pitch. atempo holds the 0.5-100 range."""
    run_ffmpeg(["ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={factor}", str(dst)])


def concat(parts: list[Path], dst: Path, sample_rate: int) -> None:
    """Joins wav files into one.

    The list of paths travels through a temporary file rather than arguments: a
    book gives thousands of chunks, and a command line cannot hold such a list.
    """
    if not parts:
        raise ValueError("nothing to join: the file list is empty")

    # The concat demuxer skips a missing file and exits with zero: the book
    # silently loses a piece. We check it ourselves, before the run.
    missing = [str(p) for p in parts if not p.exists()]
    if missing:
        raise FileNotFoundError(f"no files to join: {', '.join(missing[:5])}")

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
