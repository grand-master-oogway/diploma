"""
Shared fixtures: local storage and an in-memory fake of the GCS client (no network).
"""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from firms_ua.storage import GcsStorage, LocalStorage, Storage


class FakeBlob:
    """
    Minimal stand-in for `google.cloud.storage.Blob`.
    """

    def __init__(self, objects: dict[str, bytes], name: str) -> None:
        """
        Bind to one object name inside a bucket's dict.
        """
        self._objects = objects
        self.name = name

    def upload_from_string(self, data: bytes, content_type: str | None = None, if_generation_match: int | None = None) -> None:
        """
        Store data; fail like GCS when `if_generation_match=0` and the object exists.
        """
        if if_generation_match == 0 and self.name in self._objects:
            raise PreconditionFailed("object exists")
        self._objects[self.name] = data

    def download_as_bytes(self) -> bytes:
        """
        Return the data or raise `NotFound`.
        """
        if self.name not in self._objects:
            raise NotFound("missing")
        return self._objects[self.name]

    def exists(self) -> bool:
        """
        True if the object exists.
        """
        return self.name in self._objects


class FakeClient:
    """
    Minimal stand-in for `google.cloud.storage.Client` with one dict per bucket.
    """

    def __init__(self, project: str | None = None) -> None:
        """
        Start with no buckets (`project` is accepted and ignored, like the real client's argument).
        """
        self.buckets: dict[str, dict[str, bytes]] = {}

    def bucket(self, name: str) -> SimpleNamespace:
        """
        Return a bucket handle exposing `blob(key)`.
        """
        objects = self.buckets.setdefault(name, {})
        return SimpleNamespace(blob=lambda key: FakeBlob(objects, key))

    def list_blobs(self, bucket: str, prefix: str = "") -> list[Any]:
        """
        Return blobs whose names start with `prefix`.
        """
        objects = self.buckets.setdefault(bucket, {})
        return [SimpleNamespace(name=name) for name in objects if name.startswith(prefix)]


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
