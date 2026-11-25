"""
Tests for the storage backends (local folder and GCS through a fake client).
"""

from pathlib import Path

import pytest

from fakes import FakeClient
from firms_ua.storage.base import Storage
from firms_ua.storage.factory import open_storage
from firms_ua.storage.gcs import GcsStorage
from firms_ua.storage.local import LocalStorage


def test_put_get_exists_roundtrip(store: Storage) -> None:
    """
    Bytes come back unchanged.
    """
    payload = b"a\r\nb\x00\xff"
    assert not store.exists("x/y.bin")
    store.put_new("x/y.bin", payload)
    assert store.exists("x/y.bin")
    assert store.get("x/y.bin") == payload


def test_put_new_never_overwrites(store: Storage) -> None:
    """
    A second write to the same key fails and leaves the first object intact.
    """
    store.put_new("k", b"first")
    with pytest.raises(FileExistsError):
        store.put_new("k", b"second")
    assert store.get("k") == b"first"


def test_get_missing_raises(store: Storage) -> None:
    """
    Reading a missing key raises FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        store.get("nope")


def test_list_keys_is_recursive_sorted_and_folder_scoped(store: Storage) -> None:
    """
    A prefix lists only its own folder (not siblings that merely share the start of the name).
    """
    for key in ("a/2.txt", "a/1.txt", "a/sub/3.txt", "ab/4.txt", "b/5.txt"):
        store.put_new(key, b"x")
    assert store.list_keys("a/") == ["a/1.txt", "a/2.txt", "a/sub/3.txt"]
    assert store.list_keys("a") == ["a/1.txt", "a/2.txt", "a/sub/3.txt"]
    assert store.list_keys("missing/") == []


def test_local_leaves_no_temp_files_and_rejects_bad_keys(tmp_path: Path) -> None:
    """
    No `.tmp` files remain after writes (also failed ones); path traversal is refused.
    """
    store = LocalStorage(tmp_path)
    store.put_new("d/f", b"1")
    with pytest.raises(FileExistsError):
        store.put_new("d/f", b"2")
    assert not list(tmp_path.rglob("*.tmp"))
    with pytest.raises(ValueError, match="invalid key"):
        store.put_new("../escape", b"x")


def test_uris(tmp_path: Path, fake_gcs_store: GcsStorage) -> None:
    """
    Polars gets a local path or a gs:// URI.
    """
    assert LocalStorage(tmp_path).uri("a/b") == str(tmp_path / "a" / "b")
    assert fake_gcs_store.uri("a/b") == "gs://test-bucket/a/b"


def test_open_storage_picks_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    A local root gives one folder per layer; a gs:// root appends the layer to the bucket prefix.
    """
    local = open_storage(str(tmp_path), "raw")
    assert isinstance(local, LocalStorage)
    local.put_new("k", b"x")
    assert (tmp_path / "raw" / "k").is_file()
    monkeypatch.setattr("google.cloud.storage.Client", FakeClient)  # never build a real client in tests
    assert open_storage("gs://firms-ua-dev/", "bronze", "some-project").uri("k") == "gs://firms-ua-dev-bronze/k"


def test_impersonation_uses_the_target_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    With `impersonate`, the client gets that account's credentials; without it, the client's default ones.
    """
    asked: list[str | None] = []

    def fake_credentials(impersonate: str | None) -> str:
        asked.append(impersonate)
        return f"creds:{impersonate}"

    monkeypatch.setattr("google.cloud.storage.Client", FakeClient)
    monkeypatch.setattr("firms_ua.storage.gcs._credentials", fake_credentials)
    acting = open_storage("gs://firms-ua-dev", "silver", "p", impersonate="silver@p.iam.gserviceaccount.com")
    plain = open_storage("gs://firms-ua-dev", "silver", "p")
    assert acting._client.credentials == "creds:silver@p.iam.gserviceaccount.com"  # type: ignore[attr-defined]
    assert plain._client.credentials is None  # type: ignore[attr-defined]
    assert asked == ["silver@p.iam.gserviceaccount.com"]


def test_delete(store: Storage) -> None:
    """
    `delete` removes an object; deleting a missing key raises `FileNotFoundError`.
    """
    store.put_new("a/b", b"x")
    store.delete("a/b")
    assert not store.exists("a/b")
    with pytest.raises(FileNotFoundError):
        store.delete("a/b")
