"""Where the finished book goes.

По умолчанию папка в iCloud Drive, но она подходит не всем и не всегда.
Путь задаётся флагом, а интерфейс показывает настоящий путь, а не текст
про iCloud, написанный в разметке.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from book2audio.cli import app
from book2audio.pipeline import COPY_TO_ENV, destination
from book2audio.web.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


# --- resolving the destination ---


def test_no_copy_without_a_folder(monkeypatch):
    """The book is taken with the Download button. A copy only if it was asked for."""
    monkeypatch.delenv(COPY_TO_ENV, raising=False)
    assert destination(None) is None


def test_explicit_path_wins(tmp_path, monkeypatch):
    monkeypatch.setenv(COPY_TO_ENV, str(tmp_path / "из-окружения"))
    assert destination(tmp_path / "явный") == tmp_path / "явный"


def test_environment_is_used_when_nothing_given(tmp_path, monkeypatch):
    monkeypatch.setenv(COPY_TO_ENV, str(tmp_path / "папка"))
    assert destination(None) == tmp_path / "папка"


def test_empty_environment_means_no_copy(monkeypatch):
    monkeypatch.setenv(COPY_TO_ENV, "")
    assert destination(None) is None


def test_tilde_is_expanded(monkeypatch):
    monkeypatch.delenv(COPY_TO_ENV, raising=False)
    assert destination(Path("~/Desktop/Аудиокниги")) == Path.home() / "Desktop/Аудиокниги"


# --- CLI ---


def test_convert_copies_to_the_given_folder(tmp_path):
    target = tmp_path / "Рабочий стол" / "Аудиокниги"
    result = runner.invoke(
        app,
        [
            "convert",
            str(FIXTURES / "book_ru.fb2"),
            "--lang",
            "ru",
            "--voice",
            "fake_a",
            "--engine",
            "fake",
            "--out",
            str(tmp_path / "out"),
            "--copy-to",
            str(target),
            "--chapters",
            "1-1",
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert list(target.glob("*.m4b")), f"в {target} пусто"
    assert str(target) in result.stdout


def test_serve_help_mentions_the_folder():
    result = runner.invoke(app, ["serve", "--help"])
    assert "--copy-to" in result.stdout


# --- web ---


def test_api_reports_the_destination(tmp_path):
    target = tmp_path / "Аудиокниги"
    client_app = create_app(root=tmp_path / "root", engine_name="fake", copy_to=target)
    from fastapi.testclient import TestClient

    with TestClient(client_app) as client:
        body = client.get("/api/settings").json()
    assert body["destination"] == str(target)


def test_api_reports_no_destination_when_copying_is_off(tmp_path):
    client_app = create_app(root=tmp_path / "root", engine_name="fake", copy_to=None)
    from fastapi.testclient import TestClient

    with TestClient(client_app) as client:
        assert client.get("/api/settings").json()["destination"] is None


def test_done_screen_shows_the_real_path():
    js = (Path("book2audio/web/static/app.js")).read_text(encoding="utf-8")
    assert "/api/settings" in js
    assert "iCloud Drive → Audiobooks" not in js


@pytest.mark.parametrize("bad", ["", "   "])
def test_convert_rejects_an_empty_folder(bad, tmp_path):
    result = runner.invoke(
        app,
        [
            "convert",
            str(FIXTURES / "book_ru.fb2"),
            "--lang",
            "ru",
            "--engine",
            "fake",
            "--voice",
            "fake_a",
            "--out",
            str(tmp_path / "out"),
            "--copy-to",
            bad,
            "--chapters",
            "1-1",
        ],
    )
    assert result.exit_code != 0
