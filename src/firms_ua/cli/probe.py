"""
The `probe` command: measure source availability, NRT retention, request cost and the S-NPP gap before a backfill.
"""

import argparse

from firms_ua.common.settings import Settings
from firms_ua.firms_api.client import fetch, fetch_availability, fetch_key_status
from firms_ua.ops.probe import format_report, run_probe
from firms_ua.storage.factory import open_storage


def run(args: argparse.Namespace, settings: Settings) -> int:
    """
    Run the probe, print the report and return 0 (failed requests are part of the report, not errors).
    """
    raw = open_storage(settings.storage_root, "raw", settings.gcp_project)
    key = settings.get_map_key()
    timeout = settings.request_timeout_s
    report = run_probe(
        raw,
        get_availability=lambda: fetch_availability(key, timeout=timeout),
        get_status=lambda: fetch_key_status(key, timeout=timeout),
        fetcher=lambda window: fetch(key, window, settings.bbox, timeout=timeout, max_retries=settings.max_retries),
    )
    print(format_report(report))  # noqa: T201
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Add the command to the parser.
    """
    sub.add_parser("probe", help="measure availability, NRT retention, request cost and the S-NPP gap").set_defaults(run=run)
