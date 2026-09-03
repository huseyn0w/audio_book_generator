"""Сетевые мелочи, нужные при первой загрузке весов моделей."""

import os

import certifi


def ensure_ssl_certs() -> str:
    """Прописывает корневые сертификаты для stdlib-ssl и возвращает путь к ним.

    Standalone-сборка Python из uv не видит хранилище сертификатов macOS,
    и torch.hub падает на CERTIFICATE_VERIFY_FAILED. Значения, заданные
    снаружи, не трогаем.
    """
    path = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", path)
    return path
