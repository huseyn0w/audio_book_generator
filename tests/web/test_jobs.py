import pytest

from book2audio.web.jobs import Job, JobStore, State


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.db")


def test_new_job_starts_as_uploaded(store, tmp_path):
    job = store.create(source=tmp_path / "book.pdf", language="ru", gender="female")
    assert job.state == State.UPLOADED
    assert job.id


def test_job_can_be_read_back(store, tmp_path):
    created = store.create(source=tmp_path / "book.pdf", language="ru", gender="female")
    loaded = store.get(created.id)
    assert loaded.id == created.id
    assert loaded.language == "ru"
    assert loaded.source == tmp_path / "book.pdf"


def test_missing_job_returns_none(store):
    assert store.get("no-such-id") is None


def test_state_moves_forward(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.set_state(job.id, State.EXTRACTING)
    assert store.get(job.id).state == State.EXTRACTING


def test_finished_job_cannot_go_back_to_work(store, tmp_path):
    """Иначе повторный запрос перезапустит уже готовую книгу."""
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.set_state(job.id, State.DONE)
    with pytest.raises(ValueError, match="нельзя перевести"):
        store.set_state(job.id, State.SYNTHESIZING)


def test_failed_job_keeps_its_error(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.fail(job.id, "нет текстового слоя")
    loaded = store.get(job.id)
    assert loaded.state == State.FAILED
    assert "текстового слоя" in loaded.error


def test_progress_is_stored_and_read_back(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.set_progress(job.id, stage="synth", done=42, total=100)
    loaded = store.get(job.id)
    assert loaded.stage == "synth"
    assert loaded.done == 42
    assert loaded.total == 100


def test_cancel_flag_is_visible_to_the_worker(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.set_state(job.id, State.SYNTHESIZING)
    store.cancel(job.id)
    assert store.is_cancelled(job.id)


def test_cancelling_a_finished_job_is_refused(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.set_state(job.id, State.DONE)
    with pytest.raises(ValueError, match="нельзя перевести"):
        store.cancel(job.id)


def test_next_pending_returns_the_oldest_ready_job(store, tmp_path):
    first = store.create(source=tmp_path / "1.pdf", language="ru", gender="female")
    second = store.create(source=tmp_path / "2.pdf", language="ru", gender="female")
    store.set_state(first.id, State.READY)
    store.set_state(second.id, State.READY)
    store.mark_queued(first.id)
    store.mark_queued(second.id)
    assert store.next_queued().id == first.id


def test_next_pending_is_none_when_nothing_waits(store, tmp_path):
    store.create(source=tmp_path / "1.pdf", language="ru", gender="female")
    assert store.next_queued() is None


def test_result_path_is_remembered(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.finish(job.id, tmp_path / "book.m4b")
    loaded = store.get(job.id)
    assert loaded.state == State.DONE
    assert loaded.result == tmp_path / "book.m4b"


def test_edited_text_survives_a_restart(store, tmp_path):
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.save_review(job.id, [{"title": "Гл", "text": "Правленый текст."}])
    reopened = JobStore(tmp_path / "jobs.db")
    assert reopened.get_review(job.id)[0]["text"] == "Правленый текст."


def test_listing_returns_newest_first(store, tmp_path):
    old = store.create(source=tmp_path / "1.pdf", language="ru", gender="female")
    new = store.create(source=tmp_path / "2.pdf", language="ru", gender="female")
    ids = [j.id for j in store.recent()]
    assert ids.index(new.id) < ids.index(old.id)


def test_job_is_json_friendly(store, tmp_path):
    import json

    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    assert json.dumps(job.as_dict())


def test_store_survives_being_opened_twice(tmp_path):
    """Веб и фоновый поток открывают одну базу одновременно."""
    first = JobStore(tmp_path / "jobs.db")
    second = JobStore(tmp_path / "jobs.db")
    job = first.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    assert second.get(job.id) is not None


def test_state_values_are_stable_strings():
    assert State.UPLOADED.value == "uploaded"
    assert State.DONE.value == "done"


def test_job_dataclass_reports_whether_it_is_running():
    job = Job(id="x", source="/tmp/a.pdf", language="ru", gender="female", state=State.SYNTHESIZING)
    assert job.is_active()
    assert not Job(
        id="x", source="/tmp/a.pdf", language="ru", gender="female", state=State.DONE
    ).is_active()
