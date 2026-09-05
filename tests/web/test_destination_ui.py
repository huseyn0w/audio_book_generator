"""Выбор папки сохранения в интерфейсе.

Флаг --copy-to задаёт папку на весь запуск сервера. Через интерфейс папка
выбирается для конкретной книги: художественное на телефон, рабочее на диск.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from book2audio.web.jobs import JobStore, State
from book2audio.web.main import create_app
from book2audio.web.paths import BadDestination, resolve_destination, suggestions

FIXTURES = Path(__file__).parent.parent / "fixtures"


# --- разбор пути, пришедшего из браузера ---


def test_absolute_path_is_accepted(tmp_path):
    assert resolve_destination(str(tmp_path / "Аудиокниги")) == tmp_path / "Аудиокниги"


def test_tilde_is_expanded():
    assert resolve_destination("~/Desktop/Аудиокниги") == Path.home() / "Desktop/Аудиокниги"


def test_empty_means_the_server_default():
    assert resolve_destination("") is None
    assert resolve_destination(None) is None
    assert resolve_destination("   ") is None


def test_relative_path_is_refused():
    """Относительный путь в браузере значит что-то своё, на сервере другое."""
    with pytest.raises(BadDestination, match="полный путь"):
        resolve_destination("Аудиокниги")


def test_existing_file_is_refused(tmp_path):
    busy = tmp_path / "занято.txt"
    busy.write_text("x", encoding="utf-8")
    with pytest.raises(BadDestination, match="не папка"):
        resolve_destination(str(busy))


def test_suggestions_include_the_desktop():
    """Ключи, а не подписи: подпись выбирает интерфейс на своём языке."""
    keys = {s["key"] for s in suggestions()}
    assert keys == {"desktop", "downloads", "documents"}
    assert any("Desktop" in s["path"] for s in suggestions())


def test_suggestions_carry_no_prose():
    for item in suggestions():
        assert set(item) == {"key", "path"}


def test_suggestions_are_absolute():
    assert all(Path(s["path"]).is_absolute() for s in suggestions())


# --- база ---


def test_old_database_gets_the_new_column(tmp_path):
    """База уже существует у пользователя, ALTER TABLE обязателен."""
    path = tmp_path / "jobs.db"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, source TEXT NOT NULL, "
        "language TEXT NOT NULL, gender TEXT NOT NULL, state TEXT NOT NULL, "
        "voice TEXT, selection TEXT, audio_format TEXT NOT NULL DEFAULT 'm4b', "
        "stage TEXT NOT NULL DEFAULT '', done INTEGER NOT NULL DEFAULT 0, "
        "total INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '', "
        "result TEXT, title TEXT NOT NULL DEFAULT '', review TEXT, "
        "created_at TEXT NOT NULL);"
    )
    old.execute(
        "INSERT INTO jobs (id, source, language, gender, state, created_at) "
        "VALUES ('старая', 'книга.pdf', 'ru', 'female', 'done', '2026-01-01')"
    )
    old.commit()
    old.close()

    store = JobStore(path)
    assert store.get("старая") is not None
    assert store.get("старая").destination is None


def test_destination_is_stored_per_job(tmp_path):
    store = JobStore(tmp_path / "jobs.db")
    job = store.create(source=Path("книга.pdf"), language="ru", gender="female")
    store.set_options(job.id, voice="", selection="", audio_format="m4b", destination="/tmp/куда")
    assert store.get(job.id).destination == "/tmp/куда"


# --- HTTP ---


@pytest.fixture
def client(tmp_path):
    app = create_app(root=tmp_path, engine_name="fake", copy_to=tmp_path / "по-умолчанию")
    with TestClient(app) as ready:
        yield ready


def upload(client) -> str:
    with open(FIXTURES / "book_ru.fb2", "rb") as handle:
        response = client.post(
            "/api/jobs",
            files={"file": ("book_ru.fb2", handle, "application/octet-stream")},
            data={"language": "ru", "gender": "female"},
        )
    return response.json()["id"]


def wait_ready(client, job_id, seconds=30.0):
    import time

    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if client.get(f"/api/jobs/{job_id}").json()["state"] == State.READY.value:
            return
        time.sleep(0.05)
    raise AssertionError("задача не дошла до предпросмотра")


def test_settings_offer_folders(client):
    body = client.get("/api/settings").json()
    assert body["suggestions"]
    assert any("Desktop" in s["path"] for s in body["suggestions"])


def test_synthesize_saves_to_the_chosen_folder(client, tmp_path):
    chosen = tmp_path / "Рабочий стол" / "Аудиокниги"
    job_id = upload(client)
    wait_ready(client, job_id)
    response = client.post(f"/api/jobs/{job_id}/synthesize", json={"destination": str(chosen)})
    assert response.status_code == 202

    import time

    end = time.monotonic() + 60
    while time.monotonic() < end:
        if client.get(f"/api/jobs/{job_id}").json()["state"] == State.DONE.value:
            break
        time.sleep(0.1)
    assert list(chosen.glob("*.m4b")), f"в {chosen} пусто"
    assert not (tmp_path / "по-умолчанию").exists(), "книга ушла и в папку по умолчанию"


def test_synthesize_refuses_a_relative_folder(client):
    job_id = upload(client)
    wait_ready(client, job_id)
    response = client.post(f"/api/jobs/{job_id}/synthesize", json={"destination": "куда-то"})
    assert response.status_code == 400
    assert "полный путь" in response.json()["detail"]


def test_review_screen_has_a_folder_field():
    html = Path("book2audio/web/static/index.html").read_text(encoding="utf-8")
    js = Path("book2audio/web/static/app.js").read_text(encoding="utf-8")
    assert 'id="destination"' in html
    assert "destination" in js


def test_both_synthesis_buttons_send_the_folder():
    """Кнопка «Озвучить» и кнопка повтора должны слать одно и то же."""
    js = Path("book2audio/web/static/app.js").read_text(encoding="utf-8")
    assert js.count("destination: chosenDestination()") == 2


def test_folders_are_loaded_when_review_opens():
    js = Path("book2audio/web/static/app.js").read_text(encoding="utf-8")
    assert "loadDestinations()" in js.split("async function openReview()")[1][:200]


def test_long_paths_are_shortened_in_the_hint():
    """Путь к папке в iCloud занимает две строки и обрезается."""
    js = Path("book2audio/web/static/app.js").read_text(encoding="utf-8")
    assert "function shortPath" in js
    assert "shortPath(destination)" in js
