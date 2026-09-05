"""ffmpeg должен объяснять, почему упал.

Реальный случай: сборка книги на 13 часов упала с сообщением «exit status
255» и командной строкой. Причина (сигнал) была только в stderr, который
мы перехватывали и выбрасывали.
"""

import subprocess

import numpy as np
import pytest

from book2audio.audio import FfmpegError, change_speed, concat, run_ffmpeg, write_wav_mono16


def test_error_carries_ffmpeg_stderr(tmp_path):
    with pytest.raises(FfmpegError) as caught:
        run_ffmpeg(["ffmpeg", "-y", "-i", str(tmp_path / "нет.wav"), str(tmp_path / "out.wav")])
    assert "No such file" in str(caught.value)


def test_error_names_the_signal_when_ffmpeg_is_killed(tmp_path):
    """Код 255 сам по себе ничего не говорит. Сигнал говорит."""
    assert "255" in FfmpegError.explain(255)
    assert "сигнал" in FfmpegError.explain(255).lower()


def test_error_is_a_called_process_error(tmp_path):
    """Старый код ловил CalledProcessError, ловля не должна сломаться."""
    assert issubclass(FfmpegError, subprocess.CalledProcessError)


def test_change_speed_reports_the_reason(tmp_path):
    with pytest.raises(FfmpegError, match="No such file"):
        change_speed(tmp_path / "нет.wav", tmp_path / "out.wav", 2.0)


def test_concat_refuses_a_missing_part(tmp_path):
    """Демуксер concat пропускает несуществующий файл и выходит с нулём.

    Замер: из [a, нет, a] получается 1 секунда вместо 2. То есть пропавший
    кусок стал бы дырой в книге, и никто бы не узнал.
    """
    good = tmp_path / "a.wav"
    write_wav_mono16(good, np.zeros(24000, dtype=np.float32), 24000)
    with pytest.raises(FileNotFoundError, match="нет.wav"):
        concat([good, tmp_path / "нет.wav", good], tmp_path / "out.wav", 24000)


def test_concat_keeps_every_part(tmp_path):
    import wave

    good = tmp_path / "a.wav"
    write_wav_mono16(good, np.zeros(24000, dtype=np.float32), 24000)
    out = tmp_path / "out.wav"
    concat([good, good, good], out, 24000)
    with wave.open(str(out)) as handle:
        assert handle.getnframes() == pytest.approx(24000 * 3, rel=0.01)


def test_stderr_is_trimmed_to_the_tail(tmp_path):
    """ffmpeg сыплет сотнями строк, полезны последние."""
    noise = "\n".join(f"строка {i}" for i in range(200))
    trimmed = FfmpegError.tail(noise)
    assert "строка 199" in trimmed
    assert "строка 0" not in trimmed
    assert len(trimmed.splitlines()) <= 20
