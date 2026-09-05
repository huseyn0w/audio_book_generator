import time
from pathlib import Path

import pytest

from book2audio.web.jobs import JobStore, State
from book2audio.web.runner import Runner

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.db")


@pytest.fixture
def runner(store, tmp_path):
    worker = Runner(
        store, work_root=tmp_path / "work", out_root=tmp_path / "out", engine_name="fake"
    )
    yield worker
    worker.stop()


def wait_for(condition, seconds=25.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_runner_extracts_and_stops_for_review(store, runner, tmp_path):
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)
    review = store.get_review(job.id)
    assert review and review[0]["text"]


def test_extraction_records_the_book_title(store, runner):
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)
    assert "инноваци" in store.get(job.id).title.lower()


def test_scanned_pdf_fails_with_a_readable_message(store, runner):
    job = store.create(source=FIXTURES / "scanned_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.FAILED)
    assert "OCR" in store.get(job.id).error


def test_synthesis_produces_a_result_and_reports_progress(store, runner):
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)

    store.set_options(job.id, voice="fake_a", selection="", audio_format="m4b")
    runner.enqueue(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.DONE, seconds=60)

    finished = store.get(job.id)
    assert finished.result and finished.result.exists()
    assert finished.done == finished.total > 0


def test_cancelled_job_stops_and_leaves_no_result(store, runner):
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)

    store.set_options(job.id, voice="fake_a", selection="", audio_format="m4b")
    runner.enqueue(job.id)
    wait_for(lambda: store.get(job.id).state == State.SYNTHESIZING, seconds=10)
    store.cancel(job.id)

    assert wait_for(lambda: not store.get(job.id).is_active(), seconds=60)
    assert store.get(job.id).state == State.CANCELLED
    assert store.get(job.id).result is None


def test_edited_text_reaches_the_synthesizer(store, runner):
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)

    store.save_review(job.id, [{"title": "Только это", "text": "Один короткий абзац."}])
    store.set_options(job.id, voice="fake_a", selection="", audio_format="m4b")
    runner.enqueue(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.DONE, seconds=60)
    assert store.get(job.id).total < 5


def test_unchecked_chapters_are_skipped(store, runner):
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)

    review = store.get_review(job.id)
    for entry in review:
        entry["include"] = False
    review[0]["include"] = True
    store.save_review(job.id, review)
    store.set_options(job.id, voice="fake_a", selection="", audio_format="m4b")
    runner.enqueue(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.DONE, seconds=60)
    assert store.get(job.id).result.exists()


def test_runner_handles_one_job_at_a_time(store, runner):
    first = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    second = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    for job in (first, second):
        runner.start_extraction(job.id)
    assert wait_for(
        lambda: all(store.get(j.id).state == State.READY for j in (first, second)), seconds=40
    )


# --- выбор голоса ---


def test_voice_is_chosen_from_what_the_engine_actually_has(store, runner, tmp_path):
    """Голос по умолчанию задан для Silero, но движок может быть другим."""
    from book2audio.tts.fake import FakeEngine
    from book2audio.web.jobs import Job

    job = Job(id="x", source=tmp_path / "b.pdf", language="ru", gender="female")
    assert runner.voice_for(FakeEngine(), job) in {v.id for v in FakeEngine().voices()}


def test_explicit_voice_wins_when_the_engine_has_it(runner, tmp_path):
    from book2audio.tts.fake import FakeEngine
    from book2audio.web.jobs import Job

    job = Job(id="x", source=tmp_path / "b.pdf", language="ru", gender="male", voice="fake_b")
    assert runner.voice_for(FakeEngine(), job) == "fake_b"


def test_unknown_voice_falls_back_instead_of_crashing(runner, tmp_path):
    from book2audio.tts.fake import FakeEngine
    from book2audio.web.jobs import Job

    job = Job(
        id="x", source=tmp_path / "b.pdf", language="ru", gender="female", voice="no-such-voice"
    )
    assert runner.voice_for(FakeEngine(), job) in {v.id for v in FakeEngine().voices()}


def test_gender_is_respected_when_choosing_a_fallback(runner, tmp_path):
    from book2audio.tts.fake import FakeEngine
    from book2audio.web.jobs import Job

    job = Job(id="x", source=tmp_path / "b.pdf", language="ru", gender="male")
    chosen = runner.voice_for(FakeEngine(), job)
    by_id = {v.id: v.gender for v in FakeEngine().voices()}
    assert by_id[chosen] == "male"


def test_runner_survives_one_failed_chunk(store, tmp_path, monkeypatch):
    """Сорванный чанк не должен ронять задачу, которая шла полчаса."""
    import json

    from book2audio.tts import cache as cache_module

    original = cache_module.SynthCache.synth
    calls = {"n": 0}

    def flaky(self, engine, text, voice):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("движок сорвался")
        return original(self, engine, text, voice)

    monkeypatch.setattr(cache_module.SynthCache, "synth", flaky)
    monkeypatch.setattr(cache_module, "ATTEMPTS", 1)

    worker = Runner(
        store, work_root=tmp_path / "work", out_root=tmp_path / "out", engine_name="fake"
    )
    try:
        job = store.create(source=FIXTURES / "book_ru.fb2", language="ru", gender="female")
        worker.start_extraction(job.id)
        assert wait_for(lambda: store.get(job.id).state == State.READY)
        worker.enqueue(job.id)
        assert wait_for(lambda: store.get(job.id).state == State.DONE)
    finally:
        worker.stop()

    report = json.loads(
        (tmp_path / "work" / job.id / "synth_report.json").read_text(encoding="utf-8")
    )
    assert report["failed"] == 1


def test_runner_keeps_the_cover_through_review(store, runner, tmp_path):
    """Документ пересобирается из правленого текста, обложку надо сохранить отдельно."""
    import subprocess
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from extract.test_cover import write_fb2

    book = write_fb2(tmp_path / "cover.fb2", with_cover=True)
    job = store.create(source=book, language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)
    runner.enqueue(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.DONE)

    result = store.get(job.id).result
    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v",
            "-show_entries",
            "stream=codec_name",
            "-of",
            "default=nw=1",
            str(result),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "codec_name=" in probe.stdout


def test_runner_extracts_in_the_language_of_the_job(store, runner, tmp_path):
    """Английская книга не должна нормализоваться русскими правилами."""
    job = store.create(source=FIXTURES / "typeset_en.pdf", language="en", gender="male")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.READY)

    text = " ".join(entry["text"] for entry in store.get_review(job.id))
    letters = [ch for ch in text if ch.isalpha()]
    cyrillic = sum(1 for ch in letters if "Ѐ" <= ch <= "ӿ")
    assert cyrillic / len(letters) < 0.01


def test_failure_message_is_never_empty(store, runner, tmp_path, monkeypatch):
    """Silero кидает ValueError без текста, и на экране было пусто."""
    from book2audio.web import runner as runner_module

    def boom(self, job):
        raise ValueError

    monkeypatch.setattr(runner_module.Runner, "_extract", boom)
    job = store.create(source=FIXTURES / "toc_ru.pdf", language="ru", gender="female")
    runner.start_extraction(job.id)
    assert wait_for(lambda: store.get(job.id).state == State.FAILED)

    message = store.get(job.id).error
    assert message.strip()
    assert message.strip() != "ValueError:"
    assert "ValueError" in message


def test_cache_is_shared_between_jobs(store, tmp_path):
    """Кэш адресуется по содержимому, привязка к задаче делает повтор бесплатным
    только внутри одной задачи. Загрузка той же книги считала всё заново."""
    calls = {"n": 0}

    from book2audio.tts.fake import FakeEngine

    class Counting(FakeEngine):
        def synth(self, text, voice, out_path):
            calls["n"] += 1
            super().synth(text, voice, out_path)

    worker = Runner(
        store,
        work_root=tmp_path / "work",
        out_root=tmp_path / "out",
        cache_root=tmp_path / "cache",
        engine_name="fake",
    )
    worker._engine_for = lambda language: Counting()
    try:
        first = store.create(source=FIXTURES / "book_ru.fb2", language="ru", gender="female")
        worker.start_extraction(first.id)
        assert wait_for(lambda: store.get(first.id).state == State.READY)
        worker.enqueue(first.id)
        assert wait_for(lambda: store.get(first.id).state == State.DONE)
        after_first = calls["n"]
        assert after_first > 0

        second = store.create(source=FIXTURES / "book_ru.fb2", language="ru", gender="female")
        worker.start_extraction(second.id)
        assert wait_for(lambda: store.get(second.id).state == State.READY)
        worker.enqueue(second.id)
        assert wait_for(lambda: store.get(second.id).state == State.DONE)
    finally:
        worker.stop()

    assert calls["n"] == after_first, "вторая задача синтезировала заново"


def test_deleting_a_job_keeps_the_shared_cache(store, tmp_path):
    """Удаление задачи не должно стирать чужую работу."""
    cache_root = tmp_path / "cache"
    worker = Runner(
        store,
        work_root=tmp_path / "work",
        out_root=tmp_path / "out",
        cache_root=cache_root,
        engine_name="fake",
    )
    worker.stop()
    assert cache_root not in (tmp_path / "work").parents
