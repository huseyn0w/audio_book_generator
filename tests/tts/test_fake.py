import wave

import pytest

from book2audio.tts.base import TTSEngine
from book2audio.tts.fake import FakeEngine


def test_fake_engine_satisfies_protocol():
    assert isinstance(FakeEngine(), TTSEngine)


def test_fake_engine_lists_voices():
    assert [v.id for v in FakeEngine().voices()] == ["fake_a", "fake_b"]


def test_fake_engine_duration_is_proportional_to_text(tmp_path):
    engine = FakeEngine()
    out = tmp_path / "a.wav"
    engine.synth("x" * 150, "fake_a", out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnframes() == pytest.approx(24000 * 10, rel=0.01)


def test_fake_engine_rejects_unknown_voice(tmp_path):
    with pytest.raises(ValueError, match="unknown voice"):
        FakeEngine().synth("привет", "nope", tmp_path / "a.wav")


def test_fake_engine_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError, match="empty text"):
        FakeEngine().synth("   ", "fake_a", tmp_path / "a.wav")
