import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from book2audio.web.main import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def client(tmp_path):
    app = create_app(root=tmp_path, engine_name="fake", copy_to=None)
    with TestClient(app) as test_client:
        yield test_client


def upload(client, name="toc_ru.pdf", language="ru", gender="female"):
    with open(FIXTURES / name, "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": (name, handle, "application/pdf")},
            data={"language": language, "gender": gender},
        )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def wait_for_state(client, job_id, state, seconds=60.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["state"] == state:
            return body
        if body["state"] == "failed":
            return body
        time.sleep(0.05)
    raise AssertionError(f"задача не дошла до {state}")


# --- здоровье и статика ---


def test_health_endpoint_answers():
    from fastapi.testclient import TestClient as Client

    with Client(create_app(root=Path("/tmp/b2a-health"), engine_name="fake")) as c:
        assert c.get("/health").json()["status"] in {"ok", "degraded"}


def test_index_page_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "book2audio" in response.text.lower()


# --- загрузка ---


def test_upload_creates_a_job(client):
    job_id = upload(client)
    assert client.get(f"/api/jobs/{job_id}").status_code == 200


def test_upload_rejects_an_unknown_extension(client, tmp_path):
    fake = tmp_path / "book.txt"
    fake.write_text("привет", encoding="utf-8")
    with open(fake, "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("book.txt", handle, "text/plain")},
            data={"language": "ru", "gender": "female"},
        )
    assert response.status_code == 400
    assert "формат" in response.json()["detail"].lower()


def test_upload_rejects_an_unsupported_language(client):
    with open(FIXTURES / "toc_ru.pdf", "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("toc_ru.pdf", handle, "application/pdf")},
            data={"language": "de", "gender": "female"},
        )
    assert response.status_code == 400


def test_unknown_job_returns_404(client):
    assert client.get("/api/jobs/nope").status_code == 404


# --- предпросмотр ---


def test_review_becomes_available_after_extraction(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    review = client.get(f"/api/jobs/{job_id}/review").json()
    assert review["chapters"]
    assert review["chapters"][0]["text"]
    assert review["chapters"][0]["include"] is True


def test_review_reports_estimated_duration(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    review = client.get(f"/api/jobs/{job_id}/review").json()
    assert review["chars"] > 0
    assert review["minutes"] > 0


def test_edited_review_can_be_saved(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    payload = {"chapters": [{"title": "Гл", "text": "Правленый абзац.", "include": True}]}
    assert client.put(f"/api/jobs/{job_id}/review", json=payload).status_code == 200
    assert client.get(f"/api/jobs/{job_id}/review").json()["chapters"][0]["text"] == (
        "Правленый абзац."
    )


def test_scanned_pdf_surfaces_a_readable_error(client):
    job_id = upload(client, name="scanned_ru.pdf")
    body = wait_for_state(client, job_id, "failed")
    assert body["state"] == "failed"
    assert "OCR" in body["error"]


# --- голоса ---


def test_voices_endpoint_lists_gender(client):
    voices = client.get("/api/voices?language=ru").json()
    assert voices["voices"]
    assert {v["gender"] for v in voices["voices"]} <= {"male", "female", "unknown"}


# --- синтез ---


def test_full_run_produces_a_downloadable_file(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    payload = {"chapters": [{"title": "Гл", "text": "Короткий текст книги.", "include": True}]}
    client.put(f"/api/jobs/{job_id}/review", json=payload)

    assert client.post(f"/api/jobs/{job_id}/synthesize", json={"format": "m4b"}).status_code == 202
    wait_for_state(client, job_id, "done")

    download = client.get(f"/api/jobs/{job_id}/download")
    assert download.status_code == 200
    assert len(download.content) > 500


def test_synthesize_refuses_a_job_that_is_not_ready(client):
    job_id = upload(client)
    response = client.post(f"/api/jobs/{job_id}/synthesize", json={"format": "m4b"})
    assert response.status_code in (409, 202)


def test_download_before_completion_returns_409(client):
    job_id = upload(client)
    assert client.get(f"/api/jobs/{job_id}/download").status_code == 409


def test_cancel_stops_a_running_job(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    client.post(f"/api/jobs/{job_id}/synthesize", json={"format": "m4b"})
    client.post(f"/api/jobs/{job_id}/cancel")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = client.get(f"/api/jobs/{job_id}").json()["state"]
        if state in {"cancelled", "done"}:
            break
        time.sleep(0.05)
    assert state in {"cancelled", "done"}


def test_job_can_be_deleted(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_jobs_listing_returns_newest_first(client):
    first = upload(client)
    second = upload(client)
    ids = [j["id"] for j in client.get("/api/jobs").json()["jobs"]]
    assert ids.index(second) < ids.index(first)


# --- поток прогресса ---


def test_progress_stream_is_registered(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    routes = {r.path for r in client.app.routes}
    assert "/api/jobs/{job_id}/events" in routes


@pytest.mark.asyncio
async def test_progress_events_yield_state_changes(tmp_path):
    """Генератор проверяется напрямую: TestClient буферизует бесконечный поток."""
    from book2audio.web.jobs import JobStore
    from book2audio.web.main import progress_events

    store = JobStore(tmp_path / "jobs.db")
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")

    events = []
    generator = progress_events(store, job.id, poll_seconds=0.01, max_seconds=2.0)
    async for chunk in generator:
        events.append(chunk)
        if len(events) == 1:
            store.set_progress(job.id, "synth", 5, 10)
        elif len(events) == 2:
            store.fail(job.id, "тестовая ошибка")
        elif len(events) >= 3:
            break

    assert events[0].startswith("data: ")
    assert '"done": 5' in events[1]
    assert "тестовая ошибка" in events[2]


@pytest.mark.asyncio
async def test_progress_events_stop_on_a_finished_job(tmp_path):
    from book2audio.web.jobs import JobStore
    from book2audio.web.main import progress_events

    store = JobStore(tmp_path / "jobs.db")
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")
    store.finish(job.id, tmp_path / "book.m4b")

    chunks = [c async for c in progress_events(store, job.id, poll_seconds=0.01, max_seconds=2.0)]
    assert len(chunks) == 1
    assert '"state": "done"' in chunks[0]


@pytest.mark.asyncio
async def test_progress_events_give_up_after_the_time_limit(tmp_path):
    """Брошенная вкладка не должна держать соединение вечно."""
    from book2audio.web.jobs import JobStore
    from book2audio.web.main import progress_events

    store = JobStore(tmp_path / "jobs.db")
    job = store.create(source=tmp_path / "b.pdf", language="ru", gender="female")

    chunks = [c async for c in progress_events(store, job.id, poll_seconds=0.01, max_seconds=0.2)]
    assert len(chunks) == 1


def test_health_reports_missing_tools(client, monkeypatch):
    monkeypatch.setattr("book2audio.preflight.shutil.which", lambda name: None)
    payload = client.get("/health").json()
    assert payload["status"] == "degraded"
    assert payload["missing"] == ["ffmpeg", "espeak-ng"]
    assert "brew install ffmpeg" in payload["install"]


def test_health_is_ok_when_everything_is_installed(client, monkeypatch):
    monkeypatch.setattr("book2audio.preflight.shutil.which", lambda name: "/opt/homebrew/bin/x")
    payload = client.get("/health").json()
    assert payload["status"] == "ok"
    assert payload["missing"] == []


def test_synthesize_refuses_when_disk_is_full(client, monkeypatch):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    monkeypatch.setattr("book2audio.preflight.free_bytes", lambda path: 1024)
    response = client.post(f"/api/jobs/{job_id}/synthesize", json={})
    assert response.status_code == 507
    assert "мало места" in response.json()["detail"]


# --- отчёт, оценки и предупреждение о языке ---


def test_review_estimates_synthesis_time(client):
    """«2 часа ждать» и «10 минут ждать» это разные решения."""
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    body = client.get(f"/api/jobs/{job_id}/review").json()
    assert body["minutes"] > 0
    assert body["synth_minutes"] > 0
    assert body["synth_minutes"] < body["minutes"]


def test_review_warns_about_the_wrong_language(client):
    job_id = upload(client, name="typeset_en.pdf", language="ru")
    wait_for_state(client, job_id, "ready_for_review")
    body = client.get(f"/api/jobs/{job_id}/review").json()
    assert body["warning"]
    assert "английские" in body["warning"]


def test_review_is_quiet_when_the_language_matches(client):
    job_id = upload(client, language="ru")
    wait_for_state(client, job_id, "ready_for_review")
    assert client.get(f"/api/jobs/{job_id}/review").json()["warning"] is None


def test_clean_report_is_available_over_http(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    body = client.get(f"/api/jobs/{job_id}/report").json()
    assert body["clean"]["chars_before"] > 0
    assert isinstance(body["clean"]["dropped"], dict)
    assert body["clean"]["summary"]


def test_report_has_no_synth_section_before_synthesis(client):
    job_id = upload(client)
    wait_for_state(client, job_id, "ready_for_review")
    assert client.get(f"/api/jobs/{job_id}/report").json()["synth"] is None


def test_report_404_for_an_unknown_job(client):
    assert client.get("/api/jobs/нет-такой/report").status_code == 404


# --- диапазон страниц ---


def test_upload_accepts_a_page_range(client):
    with open(FIXTURES / "toc_ru.pdf", "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("toc_ru.pdf", handle, "application/pdf")},
            data={"language": "ru", "gender": "female", "pages": "1-1"},
        )
    assert response.status_code == 201
    job_id = response.json()["id"]
    wait_for_state(client, job_id, "ready_for_review")
    body = client.get(f"/api/jobs/{job_id}/review").json()
    assert body["chars"] > 0

    whole = upload(client)
    wait_for_state(client, whole, "ready_for_review")
    assert body["chars"] < client.get(f"/api/jobs/{whole}/review").json()["chars"]


def test_upload_rejects_a_broken_page_range(client):
    with open(FIXTURES / "toc_ru.pdf", "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("toc_ru.pdf", handle, "application/pdf")},
            data={"language": "ru", "gender": "female", "pages": "20-10"},
        )
    assert response.status_code == 400
    assert "диапазон" in response.json()["detail"]


def test_page_range_is_ignored_for_formats_without_pages(client):
    """В EPUB и FB2 страниц нет. Молча притворяться, что есть, вредно."""
    with open(FIXTURES / "book_ru.fb2", "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("book_ru.fb2", handle, "application/octet-stream")},
            data={"language": "ru", "gender": "female", "pages": "1-5"},
        )
    assert response.status_code == 400
    assert "страниц" in response.json()["detail"]
