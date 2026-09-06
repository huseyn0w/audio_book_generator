import subprocess
import wave

import numpy as np
import pytest

from book2audio.audio import change_speed, silence, write_wav_mono16


def test_write_wav_mono16_writes_correct_header(tmp_path):
    samples = np.zeros(24000, dtype=np.float32)
    out = tmp_path / "a.wav"
    write_wav_mono16(out, samples, 24000)
    with wave.open(str(out)) as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 24000
        assert w.getnframes() == 24000


def test_write_wav_mono16_clips_out_of_range(tmp_path):
    samples = np.array([2.0, -2.0], dtype=np.float32)
    out = tmp_path / "a.wav"
    write_wav_mono16(out, samples, 24000)
    with wave.open(str(out)) as w:
        data = np.frombuffer(w.readframes(2), dtype="<i2")
    assert data[0] == 32767
    assert data[1] == -32767


def test_silence_writes_requested_duration(tmp_path):
    out = tmp_path / "s.wav"
    silence(out, 0.25, 24000)
    with wave.open(str(out)) as w:
        assert w.getnframes() == 6000


def test_change_speed_halves_duration(tmp_path):
    src = tmp_path / "src.wav"
    dst = tmp_path / "dst.wav"
    write_wav_mono16(src, np.zeros(48000, dtype=np.float32), 24000)
    change_speed(src, dst, 2.0)
    with wave.open(str(dst)) as w:
        assert w.getnframes() == pytest.approx(24000, rel=0.05)


def test_change_speed_raises_on_ffmpeg_failure(tmp_path):
    src = tmp_path / "missing.wav"
    with pytest.raises(subprocess.CalledProcessError):
        change_speed(src, tmp_path / "dst.wav", 2.0)


def test_concat_joins_files_and_sums_duration(tmp_path):
    from book2audio.audio import concat

    parts = []
    for i in range(3):
        p = tmp_path / f"p{i}.wav"
        write_wav_mono16(p, np.zeros(12000, dtype=np.float32), 24000)
        parts.append(p)
    out = tmp_path / "joined.wav"
    concat(parts, out, 24000)
    with wave.open(str(out)) as w:
        assert w.getnframes() == pytest.approx(36000, rel=0.02)
        assert w.getframerate() == 24000


def test_concat_handles_more_files_than_fit_on_a_command_line(tmp_path):
    """A book gives thousands of chunks, so the file list travels in a file, not argv."""
    from book2audio.audio import concat

    parts = []
    for i in range(600):
        p = tmp_path / f"p{i:04d}.wav"
        write_wav_mono16(p, np.zeros(240, dtype=np.float32), 24000)
        parts.append(p)
    out = tmp_path / "joined.wav"
    concat(parts, out, 24000)
    with wave.open(str(out)) as w:
        assert w.getnframes() == pytest.approx(144000, rel=0.02)


def test_concat_rejects_empty_input(tmp_path):
    from book2audio.audio import concat

    with pytest.raises(ValueError, match="nothing to join"):
        concat([], tmp_path / "out.wav", 24000)
