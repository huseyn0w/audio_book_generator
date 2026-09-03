import wave

import pytest

from book2audio.tts.base import TTSEngine
from book2audio.tts.silero import SileroEngine


def test_silero_satisfies_protocol():
    assert isinstance(SileroEngine(), TTSEngine)


def test_silero_lists_voices_for_default_model():
    assert SileroEngine().voices() == ["aidar", "baya", "kseniya", "eugene", "xenia"]


def test_silero_lists_prefixed_voices_for_cis_model():
    voices = SileroEngine(model_id="v5_cis_base").voices()
    assert len(voices) == 29
    assert all(v.startswith("ru_") for v in voices)


def test_silero_rejects_unknown_model_id():
    with pytest.raises(ValueError, match="неизвестная модель"):
        SileroEngine(model_id="v9_ru")


def test_silero_rejects_unsupported_sample_rate():
    with pytest.raises(ValueError, match="частоту"):
        SileroEngine(sample_rate=44100)


def test_silero_rejects_unknown_voice(tmp_path):
    with pytest.raises(ValueError, match="неизвестный голос"):
        SileroEngine().synth("привет", "nope", tmp_path / "a.wav")


def test_silero_does_not_load_weights_in_constructor(monkeypatch):
    called = False

    def boom(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("веса не должны грузиться в конструкторе")

    monkeypatch.setattr("torch.hub.load", boom)
    SileroEngine()
    assert called is False


def test_silero_loads_repo_without_asking_stdin(monkeypatch):
    """torch.hub спрашивает подтверждение через input(). В вебе это вешает процесс."""
    captured = {}

    class DummyModel:
        def to(self, device):
            return self

    def fake_load(**kwargs):
        captured.update(kwargs)
        return DummyModel(), "example"

    monkeypatch.setattr("torch.hub.load", fake_load)
    SileroEngine()._load()

    assert captured["trust_repo"] is True
    assert captured["repo_or_dir"] == "snakers4/silero-models"
    assert captured["model"] == "silero_tts"
    assert captured["language"] == "ru"
    assert captured["speaker"] == "v5_5_ru"


def test_silero_loads_weights_only_once(monkeypatch):
    calls = 0

    class DummyModel:
        def to(self, device):
            return self

    def fake_load(**kwargs):
        nonlocal calls
        calls += 1
        return DummyModel(), "example"

    monkeypatch.setattr("torch.hub.load", fake_load)
    engine = SileroEngine()
    engine._load()
    engine._load()
    assert calls == 1


@pytest.mark.slow
def test_silero_synthesizes_russian_text(tmp_path):
    engine = SileroEngine()
    out = tmp_path / "ru.wav"
    engine.synth("Замок на двери оказался прочнее, чем ожидалось.", "xenia", out)
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getnframes() > 24000


@pytest.mark.slow
@pytest.mark.parametrize("model_id", ["v5_5_ru", "v5_cis_base"])
def test_hardcoded_voice_list_matches_model(model_id):
    """VOICES захардкожен, чтобы voices() не тянул веса. Тут сверяем с моделью."""
    from book2audio.tts.silero import VOICES

    engine = SileroEngine(model_id=model_id)
    speakers = list(engine._load().speakers)
    expected = [s for s in speakers if s.startswith("ru_")] or speakers
    assert VOICES[model_id] == expected
