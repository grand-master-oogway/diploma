"""
The storage interface the pipeline codes against.

Keys are POSIX-style paths inside a layer (for example `firms/source=X/.../requested_at=....csv`). Objects are never overwritten:
`put_new` fails if the key already exists. `delete` exists for layers that replace whole partitions (silver, gold); the
identities of the immutable layers (raw, bronze) have no delete permission.
"""

from typing import Any, Protocol


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

    def delete(self, key: str) -> None:
        """
        Remove the object; raise `FileNotFoundError` if it does not exist.
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
