"""
Choose the storage backend from the configured root.
"""

from pathlib import Path

from firms_ua.storage.base import Storage
from firms_ua.storage.gcs import GCS_SCHEME, GcsStorage
from firms_ua.storage.local import LocalStorage


def open_storage(root: str, layer: str, project: str | None = None, impersonate: str | None = None) -> Storage:
    """
    Open the storage of one medallion layer.

    Args:
        root: Either a local folder (`./data`, layers are sub-folders) or a bucket prefix (`gs://firms-ua-dev`,
            the layer is appended: `firms-ua-dev-raw`).
        layer: `raw`, `bronze`, `silver`, `gold` or `artifacts`.
        project: GCP project id (only used for `gs://` roots).
        impersonate: Service account email to act as (only used for `gs://` roots).
    """
    if root.startswith(GCS_SCHEME):
        return GcsStorage(f"{root.removeprefix(GCS_SCHEME).rstrip('/')}-{layer}", project=project, impersonate=impersonate)
    return LocalStorage(Path(root) / layer)
