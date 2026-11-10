"""
Storage in a local folder (development and tests).
"""

import os
import tempfile
from pathlib import Path
from typing import Any


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
