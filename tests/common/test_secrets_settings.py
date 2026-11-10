"""
Tests for secret reading and key loading (no network).
"""

import base64
from types import SimpleNamespace

import pytest

from firms_ua.common.secrets import clean_secret, read_secret
from firms_ua.common.settings import Settings


class FakeSession:
    """
    Stands in for an authorized session talking to the Secret Manager REST API.
    """

    def __init__(self, status: int, value: str = "") -> None:
        """
        Remember the response to give.
        """
        self.status = status
        self.value = value
        self.urls: list[str] = []

    def get(self, url: str, timeout: float) -> SimpleNamespace:
        """
        Return the canned response.
        """
        self.urls.append(url)
        payload = {"payload": {"data": base64.b64encode(self.value.encode()).decode()}}
        return SimpleNamespace(status_code=self.status, json=lambda: payload)


def test_read_secret_decodes_and_strips() -> None:
    """
    The stored value (with a stray trailing newline) comes back clean.
    """
    session = FakeSession(200, "abc123\r\n")
    assert read_secret("projects/p/secrets/s", session=session) == "abc123"
    assert session.urls == ["https://secretmanager.googleapis.com/v1/projects/p/secrets/s/versions/latest:access"]


def test_read_secret_failure_has_no_value_in_message() -> None:
    """
    A refused read raises with the status only.
    """
    with pytest.raises(RuntimeError, match="HTTP 403") as info:
        read_secret("projects/p/secrets/s", session=FakeSession(403, "topsecret"))
    assert "topsecret" not in str(info.value)


def test_settings_prefers_environment_key_then_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    FIRMS_MAP_KEY wins (and is stripped); without it the secret is read; with neither it fails clearly.
    """
    for name in ("FIRMS_MAP_KEY", "MAP_KEY", "FIRMS_MAP_KEY_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("firms_ua.common.settings.read_secret", lambda secret: f"from-{secret}")
    assert Settings(_env_file=None, map_key=" local \n").get_map_key() == "local"  # type: ignore[call-arg]
    assert Settings(_env_file=None, map_key_secret="projects/p/secrets/s").get_map_key() == "from-projects/p/secrets/s"  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="FIRMS_MAP_KEY"):
        Settings(_env_file=None).get_map_key()  # type: ignore[call-arg]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("abc", "abc"),
        (" abc\r\n", "abc"),
        ("﻿abc", "abc"),
        ('"abc"', "abc"),
        ('﻿"abc"\n', "abc"),
        ("'abc'", "abc"),
        ('"abc', '"abc'),
    ],
)
def test_clean_secret(raw: str, expected: str) -> None:
    """
    Whitespace, a BOM and matching surrounding quotes are removed; unbalanced quotes are left alone.
    """
    assert clean_secret(raw) == expected


def test_read_secret_cleans_bom_and_quotes() -> None:
    """
    A secret stored as BOM + quoted value (as found in the dev project) still reads back correctly.
    """
    assert read_secret("projects/p/secrets/s", session=FakeSession(200, '﻿"abc123"')) == "abc123"
