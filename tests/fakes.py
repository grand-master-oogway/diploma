"""
In-memory fake of the GCS client (no network).
"""

from types import SimpleNamespace
from typing import Any

from google.api_core.exceptions import NotFound, PreconditionFailed


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

    def delete(self) -> None:
        """
        Remove the object or raise `NotFound`.
        """
        if self._objects.pop(self.name, None) is None:
            raise NotFound("missing")

    def exists(self) -> bool:
        """
        True if the object exists.
        """
        return self.name in self._objects


class FakeClient:
    """
    Minimal stand-in for `google.cloud.storage.Client` with one dict per bucket.
    """

    def __init__(self, project: str | None = None, credentials: object | None = None) -> None:
        """
        Start with no buckets; `project` and `credentials` are recorded, like the real client's arguments.
        """
        self.buckets: dict[str, dict[str, bytes]] = {}
        self.project = project
        self.credentials = credentials

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
