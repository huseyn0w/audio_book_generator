"""Small network details needed the first time model weights are downloaded."""

import os

import certifi


def ensure_ssl_certs() -> str:
    """Points stdlib ssl at the root certificates and returns their path.

    The standalone Python build from uv cannot see the macOS certificate
    store, so torch.hub fails with CERTIFICATE_VERIFY_FAILED. Values set
    from outside are left alone.
    """
    path = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", path)
    return path
