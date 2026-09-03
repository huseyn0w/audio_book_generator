import os
from pathlib import Path

from book2audio.net import ensure_ssl_certs


def test_ensure_ssl_certs_points_at_real_bundle(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    path = ensure_ssl_certs()
    assert Path(path).is_file()
    assert os.environ["SSL_CERT_FILE"] == path
    assert os.environ["REQUESTS_CA_BUNDLE"] == path


def test_ensure_ssl_certs_does_not_override_existing_env(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/custom/ca.pem")
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    ensure_ssl_certs()
    assert os.environ["SSL_CERT_FILE"] == "/custom/ca.pem"
