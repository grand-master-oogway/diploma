"""
Storage in a Google Cloud Storage bucket.
"""

from collections.abc import Callable
from datetime import UTC
from typing import Any

GCS_SCHEME = "gs://"
_GCS_SCOPES = ["https://www.googleapis.com/auth/devstorage.read_write"]


def _credentials(impersonate: str | None) -> Any:  # noqa: ANN401  (google-auth credentials have no common public type)
    """
    Return Application Default Credentials, or credentials of `impersonate` (a service account email) obtained with them.

    Impersonation lets one process act as a stage's own service account (for example `silver`) without a key file.
    """
    import google.auth  # noqa: PLC0415
    from google.auth import impersonated_credentials  # noqa: PLC0415

    source, _ = google.auth.default(scopes=_GCS_SCOPES)
    if impersonate is None:
        return source
    return impersonated_credentials.Credentials(source_credentials=source, target_principal=impersonate, target_scopes=_GCS_SCOPES)


def _polars_credentials(impersonate: str | None) -> Callable[[], tuple[dict[str, str], int | None]]:
    """
    Return a Polars credential provider: a bearer token and its expiry (epoch seconds).

    Polars' own helper needs the system time-zone database, which Windows lacks, so we ask google-auth directly.
    """

    def provide() -> tuple[dict[str, str], int | None]:
        from google.auth.transport.requests import Request  # noqa: PLC0415

        credentials = _credentials(impersonate)
        credentials.refresh(Request())
        expiry = credentials.expiry.replace(tzinfo=UTC) if credentials.expiry else None
        return {"bearer_token": credentials.token}, int(expiry.timestamp()) if expiry else None

    return provide


class GcsStorage:
    """
    A GCS bucket, accessed with Application Default Credentials (optionally impersonating a service account).

    Writes use `if_generation_match=0`, so an existing object is never replaced.
    """

    def __init__(
        self,
        bucket: str,
        client: Any | None = None,  # noqa: ANN401
        project: str | None = None,
        impersonate: str | None = None,
    ) -> None:
        """
        Open `bucket`.

        `client` is injectable for tests, `project` is the billing/quota project, `impersonate` a service account email
        to act as (used for both the client and Polars reads).
        """
        if client is None:
            from google.cloud import storage  # noqa: PLC0415  (imported lazily: only needed for gs:// roots)

            client = storage.Client(project=project, credentials=_credentials(impersonate) if impersonate else None)
        self._bucket_name = bucket
        self._client = client
        self._impersonate = impersonate

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

    def delete(self, key: str) -> None:
        """
        Remove the object; raise `FileNotFoundError` if it does not exist.
        """
        from google.api_core.exceptions import NotFound  # noqa: PLC0415

        try:
            self._blob(key).delete()
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
        return {"credential_provider": _polars_credentials(self._impersonate)}
