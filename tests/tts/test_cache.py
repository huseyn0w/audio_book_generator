import pytest

from book2audio.tts.cache import SynthCache
from book2audio.tts.fake import FakeEngine


def test_key_is_stable_for_the_same_input(tmp_path):
    cache = SynthCache(tmp_path)
    engine = FakeEngine()
    assert cache.key("привет", "fake_a", engine) == cache.key("привет", "fake_a", engine)


def test_key_changes_with_text(tmp_path):
    cache, engine = SynthCache(tmp_path), FakeEngine()
    assert cache.key("привет", "fake_a", engine) != cache.key("пока", "fake_a", engine)


def test_key_changes_with_voice(tmp_path):
    cache, engine = SynthCache(tmp_path), FakeEngine()
    assert cache.key("привет", "fake_a", engine) != cache.key("привет", "fake_b", engine)


def test_key_changes_with_engine_version(tmp_path):
    """Смена модели обязана инвалидировать кэш, иначе книга склеится из старых кусков."""
    cache = SynthCache(tmp_path)
    old, new = FakeEngine(), FakeEngine()
    new.version = "v2"
    assert cache.key("привет", "fake_a", old) != cache.key("привет", "fake_a", new)


def test_first_call_synthesizes_and_writes_the_file(tmp_path):
    cache = SynthCache(tmp_path)
    path = cache.synth(FakeEngine(), "привет", "fake_a")
    assert path.exists()
    assert cache.misses == 1
    assert cache.hits == 0


def test_second_call_reuses_the_file_without_synthesizing(tmp_path):
    calls = 0

    class Counting(FakeEngine):
        def synth(self, text, voice, out_path):
            nonlocal calls
            calls += 1
            super().synth(text, voice, out_path)

    cache = SynthCache(tmp_path)
    engine = Counting()
    first = cache.synth(engine, "привет", "fake_a")
    second = cache.synth(engine, "привет", "fake_a")

    assert first == second
    assert calls == 1
    assert cache.hits == 1
    assert cache.misses == 1


def test_failed_synthesis_leaves_no_partial_file(tmp_path):
    """Оборванный wav в кэше хуже отсутствующего: он молча попадёт в книгу."""

    class Broken(FakeEngine):
        def synth(self, text, voice, out_path):
            out_path.write_bytes(b"garbage")
            raise RuntimeError("движок упал")

    cache = SynthCache(tmp_path)
    with pytest.raises(RuntimeError):
        cache.synth(Broken(), "привет", "fake_a")
    assert list(tmp_path.glob("*.wav")) == []


def test_cache_creates_its_directory(tmp_path):
    root = tmp_path / "nested" / "cache"
    SynthCache(root).synth(FakeEngine(), "привет", "fake_a")
    assert root.is_dir()
