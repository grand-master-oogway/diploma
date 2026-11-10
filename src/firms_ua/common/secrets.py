"""
Read secrets from GCP Secret Manager with Application Default Credentials (REST, no extra dependency).
"""

import base64
from typing import Any

_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]
_API = "https://secretmanager.googleapis.com/v1"


def clean_secret(value: str) -> str:
    """
    Remove what commonly sticks to a pasted secret: whitespace, a byte-order mark and surrounding quotes.
    """
    cleaned = value.strip().lstrip("\ufeff").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in "\"'":
        cleaned = cleaned[1:-1].strip()
    return cleaned


def read_secret(secret: str, session: Any | None = None, timeout: float = 30.0) -> str:  # noqa: ANN401
    """
    Return the latest version of a secret as clean text (see `clean_secret`).

    Args:
        secret: Resource name, for example `projects/nasa-firms/secrets/firms-ua-dev-map-key`.
        session: An authorized `requests`-style session (injectable for tests); the default uses ADC.
        timeout: Request timeout in seconds.

    Raises:
        RuntimeError: If the secret cannot be read (the message never contains the secret value).
    """
    if session is None:
        import google.auth  # noqa: PLC0415
        from google.auth.transport.requests import AuthorizedSession  # noqa: PLC0415

        credentials, _ = google.auth.default(scopes=_SCOPES)
        session = AuthorizedSession(credentials)
    response = session.get(f"{_API}/{secret}/versions/latest:access", timeout=timeout)
    if response.status_code != 200:
        msg = f"cannot read secret {secret}: HTTP {response.status_code}"
        raise RuntimeError(msg)
    return clean_secret(base64.b64decode(response.json()["payload"]["data"]).decode("utf-8"))
