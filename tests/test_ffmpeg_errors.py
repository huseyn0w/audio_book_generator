"""ffmpeg has to explain why it failed.

A real case: a 13 hour book build died with the message "exit status 255" and a
command line. The cause, a signal, was only in stderr, which we captured and
threw away.
"""

import subprocess

import numpy as np
import pytest

from book2audio.audio import FfmpegError, change_speed, concat, run_ffmpeg, write_wav_mono16


def test_error_carries_ffmpeg_stderr(tmp_path):
    with pytest.raises(FfmpegError) as caught:
        run_ffmpeg(["ffmpeg", "-y", "-i", str(tmp_path / "missing.wav"), str(tmp_path / "out.wav")])
    assert "No such file" in str(caught.value)


def test_error_names_the_signal_when_ffmpeg_is_killed(tmp_path):
    """Code 255 on its own says nothing. The signal says something."""
    assert "255" in FfmpegError.explain(255)
    assert "signal" in FfmpegError.explain(255).lower()


def test_error_is_a_called_process_error(tmp_path):
    """The old code caught CalledProcessError, and that catch must keep working."""
    assert issubclass(FfmpegError, subprocess.CalledProcessError)


def test_change_speed_reports_the_reason(tmp_path):
    with pytest.raises(FfmpegError, match="No such file"):
        change_speed(tmp_path / "missing.wav", tmp_path / "out.wav", 2.0)


def test_concat_refuses_a_missing_part(tmp_path):
    """The concat demuxer skips a missing file and exits with zero.

    Measured: [a, missing, a] gives 1 second instead of 2. The lost piece would
    become a hole in the book and nobody would find out.
    """
    good = tmp_path / "a.wav"
    write_wav_mono16(good, np.zeros(24000, dtype=np.float32), 24000)
    with pytest.raises(FileNotFoundError, match="missing.wav"):
        concat([good, tmp_path / "missing.wav", good], tmp_path / "out.wav", 24000)


def test_concat_keeps_every_part(tmp_path):
    import wave

    good = tmp_path / "a.wav"
    write_wav_mono16(good, np.zeros(24000, dtype=np.float32), 24000)
    out = tmp_path / "out.wav"
    concat([good, good, good], out, 24000)
    with wave.open(str(out)) as handle:
        assert handle.getnframes() == pytest.approx(24000 * 3, rel=0.01)


def test_stderr_is_trimmed_to_the_tail(tmp_path):
    """ffmpeg pours out hundreds of lines, and the last ones are the useful ones."""
    noise = "\n".join(f"line {i}" for i in range(200))
    trimmed = FfmpegError.tail(noise)
    assert "line 199" in trimmed
    assert "line 0" not in trimmed
    assert len(trimmed.splitlines()) <= 20
