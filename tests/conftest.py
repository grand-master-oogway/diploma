"""
Shared fixtures: local storage and an in-memory fake of the GCS client (no network).
"""

from pathlib import Path

import pytest

from fakes import FakeClient
from firms_ua.storage.base import Storage
from firms_ua.storage.gcs import GcsStorage
from firms_ua.storage.local import LocalStorage


@pytest.fixture
def local_store(tmp_path: Path) -> LocalStorage:
    """
    A storage backed by a temporary folder.
    """
    return LocalStorage(tmp_path)


@pytest.fixture
def fake_gcs_store() -> GcsStorage:
    """
    A GCS storage talking to the in-memory fake.
    """
    return GcsStorage("test-bucket", client=FakeClient())


@pytest.fixture(params=["local", "fake_gcs"])
def store(request: pytest.FixtureRequest, local_store: LocalStorage, fake_gcs_store: GcsStorage) -> Storage:
    """
    Every backend, so the same test runs against all of them.
    """
    return local_store if request.param == "local" else fake_gcs_store
