"""
Object storage backends: a local folder or a GCS bucket, one `Storage` per medallion layer.

Keys are POSIX-style paths inside the layer (for example `firms/source=X/.../requested_at=....csv`). Objects are never
overwritten: `put_new` fails if the key already exists.
"""

import os
import tempfile
from datetime import UTC
from pathlib import Path
from typing import Any, Protocol

GCS_SCHEME = "gs://"
_GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.read_write"]


def _gcp_credentials() -> tuple[dict[str, str], int | None]:
    """
    Return a bearer token from Application Default Credentials and its expiry (epoch seconds) for Polars.

    Polars' own helper needs the system time-zone database, which Windows lacks, so we ask google-auth directly.
    """
    import google.auth  # noqa: PLC0415
    from google.auth.transport.requests import Request  # noqa: PLC0415

    credentials, _ = google.auth.default(scopes=_GCS_SCOPES)
    credentials.refresh(Request())
    expiry = credentials.expiry.replace(tzinfo=UTC) if credentials.expiry else None
    return {"bearer_token": credentials.token}, int(expiry.timestamp()) if expiry else None


class Storage(Protocol):
    """
    What the pipeline needs from a storage backend.
    """

    def put_new(self, key: str, data: bytes) -> None:
        """
        Store `data` under `key`; raise `FileExistsError` if the key already exists.
        """
        ...

    def get(self, key: str) -> bytes:
        """
        Return the object's bytes; raise `FileNotFoundError` if it does not exist.
        """
        ...

    def exists(self, key: str) -> bool:
        """
        True if the key exists.
        """
        ...

    def list_keys(self, prefix: str) -> list[str]:
        """
        Return all keys under the folder `prefix` (for example `firms/source=X/`), sorted, recursively.
        """
        ...

    def uri(self, key: str) -> str:
        """
        Return a location Polars can read (a local path or a `gs://` URI).
        """
        ...

    def polars_options(self) -> dict[str, Any]:
        """
        Return extra keyword arguments for `pl.scan_parquet` (credentials for remote backends).
        """
        ...


class LocalStorage:
    """
    A folder on disk. Writes go through a temp file and a hard link, so a key is never replaced and never half-written.
    """

    def __init__(self, root: Path) -> None:
        """
        Use `root` as the folder that holds all keys.
        """
        self._root = root

    def _path(self, key: str) -> Path:
        if key.startswith("/") or ".." in key.split("/"):
            msg = f"invalid key: {key!r}"
            raise ValueError(msg)
        return self._root / key

    def put_new(self, key: str, data: bytes) -> None:
        """
        Store `data` under `key`; raise `FileExistsError` if the key already exists.
        """
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.link(tmp_name, target)  # raises FileExistsError if target exists
        finally:
            Path(tmp_name).unlink(missing_ok=True)

    def get(self, key: str) -> bytes:
        """
        Return the object's bytes; raise `FileNotFoundError` if it does not exist.
        """
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        """
        True if the key exists.
        """
        return self._path(key).is_file()

    def list_keys(self, prefix: str) -> list[str]:
        """
        Return all keys under the folder `prefix`, sorted, recursively.
        """
        base = self._path(prefix.rstrip("/")) if prefix.strip("/") else self._root
        if not base.is_dir():
            return []
        return sorted(p.relative_to(self._root).as_posix() for p in base.rglob("*") if p.is_file() and not p.name.endswith(".tmp"))

    def uri(self, key: str) -> str:
        """
        Return the local path as a string.
        """
        return str(self._path(key))

    def polars_options(self) -> dict[str, Any]:
        """
        No extra options for local files.
        """
        return {}


class GcsStorage:
    """
    A GCS bucket, accessed with Application Default Credentials.

    Writes use `if_generation_match=0`, so an existing object is never replaced.
    """

    def __init__(self, bucket: str, client: Any | None = None, project: str | None = None) -> None:  # noqa: ANN401
        """
        Open `bucket`; `client` is injectable for tests, `project` is the billing/quota project.
        """
        if client is None:
            from google.cloud import storage  # noqa: PLC0415  (imported lazily: only needed for gs:// roots)

            client = storage.Client(project=project)
        self._bucket_name = bucket
        self._client = client

    def _blob(self, key: str) -> Any:  # noqa: ANN401
        return self._client.bucket(self._bucket_name).blob(key)

    def put_new(self, key: str, data: bytes) -> None:
        """
        Store `data` under `key`; raise `FileExistsError` if the object already exists.
        """
        from google.api_core.exceptions import PreconditionFailed  # noqa: PLC0415

        try:
            self._blob(key).upload_from_string(data, content_type="application/octet-stream", if_generation_match=0)
        except PreconditionFailed:
            msg = f"object already exists: gs://{self._bucket_name}/{key}"
            raise FileExistsError(msg) from None

    def get(self, key: str) -> bytes:
        """
        Return the object's bytes; raise `FileNotFoundError` if it does not exist.
        """
        from google.api_core.exceptions import NotFound  # noqa: PLC0415

        try:
            return self._blob(key).download_as_bytes()
        except NotFound:
            msg = f"no such object: gs://{self._bucket_name}/{key}"
            raise FileNotFoundError(msg) from None

    def exists(self, key: str) -> bool:
        """
        True if the object exists.
        """
        return bool(self._blob(key).exists())

    def list_keys(self, prefix: str) -> list[str]:
        """
        Return all object names under the folder `prefix`, sorted.
        """
        folder = prefix.strip("/")
        folder = f"{folder}/" if folder else ""
        return sorted(blob.name for blob in self._client.list_blobs(self._bucket_name, prefix=folder))

    def uri(self, key: str) -> str:
        """
        Return the `gs://` URI of the key.
        """
        return f"{GCS_SCHEME}{self._bucket_name}/{key}"

    def polars_options(self) -> dict[str, Any]:
        """
        Let Polars authenticate with Application Default Credentials.
        """
        return {"credential_provider": _gcp_credentials}


def open_storage(root: str, layer: str, project: str | None = None) -> Storage:
    """
    Open the storage of one medallion layer.

    Args:
        root: Either a local folder (`./data`, layers are sub-folders) or a bucket prefix (`gs://firms-ua-dev`,
            the layer is appended: `firms-ua-dev-raw`).
        layer: `raw`, `bronze`, `silver`, `gold` or `artifacts`.
        project: GCP project id (only used for `gs://` roots).
    """
    if root.startswith(GCS_SCHEME):
        return GcsStorage(f"{root.removeprefix(GCS_SCHEME).rstrip('/')}-{layer}", project=project)
    return LocalStorage(Path(root) / layer)
