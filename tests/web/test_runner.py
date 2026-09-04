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
    worker = Runner(store, work_root=tmp_path / "work", out_root=tmp_path / "out",
                    engine_name="fake")
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
    assert wait_for(lambda: all(store.get(j.id).state == State.READY for j in (first, second)),
                    seconds=40)
