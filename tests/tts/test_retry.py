"""One failed chunk must not cost the whole book."""

import wave
from pathlib import Path

import pytest

from book2audio.tts.cache import SynthCache
from book2audio.tts.fake import FakeEngine


class FlakyEngine(FakeEngine):
    """Fails a given number of times, then synthesizes normally."""

    def __init__(self, failures: int) -> None:
        self.left = failures
        self.calls = 0

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        self.calls += 1
        if self.left > 0:
            self.left -= 1
            raise RuntimeError("движок сорвался")
        super().synth(text, voice, out_path)


def duration(path: Path) -> float:
    with wave.open(str(path)) as handle:
        return handle.getnframes() / handle.getframerate()


def test_retry_succeeds_on_second_attempt(tmp_path):
    engine = FlakyEngine(failures=1)
    cache = SynthCache(tmp_path)
    path = cache.synth_or_silence(engine, "привет" * 20, "fake_a")
    assert engine.calls == 2
    assert cache.failures == []
    assert duration(path) > 0.5


def test_falls_back_to_silence_after_three_attempts(tmp_path):
    engine = FlakyEngine(failures=99)
    cache = SynthCache(tmp_path)
    path = cache.synth_or_silence(engine, "x" * 150, "fake_a")
    assert engine.calls == 3
    assert cache.failures == ["x" * 150]
    assert duration(path) == pytest.approx(10.0, rel=0.01)


def test_silence_keeps_engine_sample_rate(tmp_path):
    path = SynthCache(tmp_path).synth_or_silence(FlakyEngine(failures=99), "текст", "fake_a")
    with wave.open(str(path)) as handle:
        assert handle.getframerate() == FakeEngine.sample_rate
        assert handle.getnchannels() == 1


def test_bad_voice_is_not_retried(tmp_path):
    """An unknown voice is not fixed by a retry, and silence would hide the error."""
    cache = SynthCache(tmp_path)
    with pytest.raises(ValueError, match="unknown voice"):
        cache.synth_or_silence(FakeEngine(), "привет", "нет такого")
    assert cache.failures == []


def test_failed_chunk_is_not_cached_as_silence(tmp_path):
    """Silence sits apart: once the engine is fixed the book has to synthesize again."""
    cache = SynthCache(tmp_path)
    cache.synth_or_silence(FlakyEngine(failures=99), "привет", "fake_a")
    assert not cache.path("привет", "fake_a", FakeEngine()).exists()


def test_report_lists_failed_chunks(tmp_path):
    cache = SynthCache(tmp_path)
    cache.synth_or_silence(FlakyEngine(failures=99), "первый" * 30, "fake_a")
    cache.synth_or_silence(FakeEngine(), "второй", "fake_a")
    report = cache.report()
    assert report["failed"] == 1
    assert report["chunks"][0].startswith("первый")
    assert len(report["chunks"][0]) <= 200


class ValueErrorEngine(FakeEngine):
    """The engine throws a bare ValueError, like the real Silero on a bad piece."""

    def __init__(self) -> None:
        self.calls = 0

    def synth(self, text: str, voice: str, out_path: Path) -> None:
        self.calls += 1
        raise ValueError


def test_value_error_from_the_engine_is_retried(tmp_path):
    """Silero throws a bare ValueError on a piece it could not parse.

    Раньше он пролетал мимо повторов и ронял всю книгу на 1846 кусков.
    """
    engine = ValueErrorEngine()
    cache = SynthCache(tmp_path)
    path = cache.synth_or_silence(engine, "любой текст", "fake_a")
    assert engine.calls == 3
    assert cache.failures == ["любой текст"]
    assert path.exists()


def test_unknown_voice_is_still_rejected_immediately(tmp_path):
    """We check the voice ourselves, before the engine: silence for a whole book is no answer."""
    engine = ValueErrorEngine()
    cache = SynthCache(tmp_path)
    with pytest.raises(ValueError, match="unknown voice"):
        cache.synth_or_silence(engine, "текст", "нет такого")
    assert engine.calls == 0


def test_empty_text_is_rejected_without_calling_the_engine(tmp_path):
    engine = ValueErrorEngine()
    with pytest.raises(ValueError, match="empty text"):
        SynthCache(tmp_path).synth_or_silence(engine, "   ", "fake_a")
    assert engine.calls == 0
