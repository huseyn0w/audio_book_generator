"""Образец голоса. Выбирать диктора по имени в выпадающем списке бессмысленно."""

import wave
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from book2audio.web.main import SAMPLE_TEXT, create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(root=tmp_path, engine_name="fake", copy_to=None)
    with TestClient(app) as test_client:
        yield test_client


def test_sample_returns_wav(client):
    response = client.get("/api/sample", params={"language": "ru", "voice": "fake_a"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    with wave.open(BytesIO(response.content)) as handle:
        assert handle.getnchannels() == 1
        assert handle.getnframes() > 0


def test_sample_rejects_unknown_voice(client):
    response = client.get("/api/sample", params={"language": "ru", "voice": "нет такого"})
    assert response.status_code == 400


def test_sample_rejects_unknown_language(client):
    response = client.get("/api/sample", params={"language": "de", "voice": "fake_a"})
    assert response.status_code == 400


def test_sample_is_synthesized_once(client, tmp_path):
    """Silero на этой фразе тратит секунду. Второй раз ждать незачем."""
    client.get("/api/sample", params={"language": "ru", "voice": "fake_a"})
    files = sorted((tmp_path / "samples").rglob("*.wav"))
    assert len(files) == 1
    stamp = files[0].stat().st_mtime_ns

    client.get("/api/sample", params={"language": "ru", "voice": "fake_a"})
    assert files[0].stat().st_mtime_ns == stamp


def test_sample_text_exists_for_both_languages():
    assert set(SAMPLE_TEXT) == {"ru", "en"}
    for text in SAMPLE_TEXT.values():
        assert 40 < len(text) < 300


def test_frontend_has_a_listen_button():
    static = Path("book2audio/web/static")
    assert 'id="listen"' in (static / "index.html").read_text(encoding="utf-8")
    assert "/api/sample" in (static / "app.js").read_text(encoding="utf-8")
