"""
Dagster resource giving assets the settings, storages and the throttled FIRMS fetcher.

The MAP_KEY is read at run time (environment or Secret Manager through the VM's service account). It never enters run
config, asset metadata or logs: the client redacts URLs in its errors.
"""

import time
from collections.abc import Callable

import dagster as dg

from firms_ua.common.settings import Settings
from firms_ua.common.windows import Window
from firms_ua.firms_api.client import fetch
from firms_ua.firms_api.models import FirmsResponse
from firms_ua.ingestion.throttle import TransactionBudget, request_cost
from firms_ua.storage.base import Storage
from firms_ua.storage.factory import open_storage

type Fetcher = Callable[[Window], FirmsResponse]


class FirmsPipeline(dg.ConfigurableResource):
    """
    Entry point to the pipeline's configuration and I/O; all values come from `FIRMS_*` environment variables.
    """

    def settings(self) -> Settings:
        """
        Read the settings from the environment.
        """
        return Settings()

    def storage(self, settings: Settings, layer: str, *, impersonate: str | None = None) -> Storage:
        """
        Open one layer's storage, optionally acting as another service account (`impersonate`, an email).
        """
        return open_storage(settings.storage_root, layer, settings.gcp_project, impersonate)

    def fetcher(self, settings: Settings) -> Fetcher:
        """
        Return a fetcher that waits for the MAP_KEY budget before each request.
        """
        key = settings.get_map_key()
        budget = TransactionBudget(settings.budget_transactions, settings.budget_period_s, clock=time.monotonic, sleep=time.sleep)

        def run(window: Window) -> FirmsResponse:
            budget.acquire(request_cost(window.day_range))
            return fetch(key, window, settings.bbox, timeout=settings.request_timeout_s, max_retries=settings.max_retries)

        return run
