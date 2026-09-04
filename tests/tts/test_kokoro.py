import wave

import pytest

from book2audio.tts.base import TTSEngine
from book2audio.tts.kokoro import KokoroEngine


def test_kokoro_satisfies_protocol():
    assert isinstance(KokoroEngine(), TTSEngine)


def test_kokoro_sample_rate_is_24000():
    assert KokoroEngine().sample_rate == 24000


def test_kokoro_lists_american_and_british_voices():
    ids = [v.id for v in KokoroEngine().voices()]
    assert "af_heart" in ids
    assert "bm_george" in ids


def test_kokoro_rejects_unknown_voice(tmp_path):
    with pytest.raises(ValueError, match="неизвестный голос"):
        KokoroEngine().synth("hello", "nope", tmp_path / "a.wav")


def test_kokoro_rejects_empty_text(tmp_path):
    with pytest.raises(ValueError, match="пустой текст"):
        KokoroEngine().synth("  ", "af_heart", tmp_path / "a.wav")


def test_kokoro_picks_lang_code_from_voice_prefix():
    engine = KokoroEngine()
    assert engine._lang_code("af_heart") == "a"
    assert engine._lang_code("bm_george") == "b"


def test_kokoro_does_not_load_weights_in_constructor(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("веса не должны грузиться в конструкторе")

    monkeypatch.setattr("mlx_audio.tts.utils.load_model", boom)
    KokoroEngine()


def test_kokoro_concatenates_generator_chunks(tmp_path, monkeypatch):
    """generate() отдаёт длинный текст кусками, их надо склеить в один wav."""
    import numpy as np

    class Result:
        def __init__(self, audio):
            self.audio = audio

    class DummyModel:
        def generate(self, **kwargs):
            yield Result(np.zeros(24000, dtype=np.float32))
            yield Result(np.zeros(12000, dtype=np.float32))

    engine = KokoroEngine()
    monkeypatch.setattr(engine, "_load", lambda: DummyModel())
    out = tmp_path / "a.wav"
    engine.synth("hello there", "af_heart", out)
    with wave.open(str(out)) as w:
        assert w.getnframes() == 36000


def test_kokoro_raises_when_generator_is_empty(tmp_path, monkeypatch):
    class DummyModel:
        def generate(self, **kwargs):
            return iter(())

    engine = KokoroEngine()
    monkeypatch.setattr(engine, "_load", lambda: DummyModel())
    with pytest.raises(RuntimeError, match="ничего не выдал"):
        engine.synth("hello", "af_heart", tmp_path / "a.wav")


@pytest.mark.slow
def test_kokoro_synthesizes_english_text(tmp_path):
    engine = KokoroEngine()
    out = tmp_path / "en.wav"
    engine.synth("The lock on the door proved sturdier than expected.", "af_heart", out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getnframes() > 24000
