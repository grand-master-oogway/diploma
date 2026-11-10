"""
The `fetch`, `build-bronze` and `ingest` commands.

- `fetch`: FIRMS API -> raw layer (CSV bytes), logged in the ingestion log.
- `build-bronze`: raw layer -> bronze layer (Parquet), logged in the ingestion log.
- `ingest`: both steps.
"""

import argparse
import logging
from datetime import date

from firms_ua.common.settings import Settings
from firms_ua.common.windows import Window, plan_windows
from firms_ua.firms_api.client import fetch
from firms_ua.firms_api.models import FirmsResponse
from firms_ua.ingestion.runner import StepReport, build_objects, fetch_windows
from firms_ua.raw.store import list_raw
from firms_ua.storage.factory import open_storage

log = logging.getLogger(__name__)


def _fetch(args: argparse.Namespace, settings: Settings) -> StepReport:
    raw = open_storage(settings.storage_root, "raw", settings.gcp_project)
    key = settings.get_map_key()

    def fetcher(window: Window) -> FirmsResponse:
        return fetch(key, window, settings.bbox, timeout=settings.request_timeout_s, max_retries=settings.max_retries)

    windows = plan_windows(args.source, args.start, args.end or args.start, settings.max_day_range)
    report = fetch_windows(raw, windows, fetcher, force=args.force)
    log.info("fetch finished: %d fetched, %d skipped, %d failed", report.done, report.skipped, report.failed)
    return report


def _build_bronze(args: argparse.Namespace, settings: Settings) -> StepReport:
    raw = open_storage(settings.storage_root, "raw", settings.gcp_project)
    bronze = open_storage(settings.storage_root, "bronze", settings.gcp_project)
    objects = list_raw(raw, args.source, args.start, args.end or args.start)
    if not objects:
        log.warning("no raw objects for %s in the requested range", args.source)
    report = build_objects(raw, bronze, objects)
    log.info("build-bronze finished: %d built, %d skipped, %d failed", report.done, report.skipped, report.failed)
    return report


def run_fetch(args: argparse.Namespace, settings: Settings) -> int:
    """
    Run `fetch`; return the number of failed windows.
    """
    return _fetch(args, settings).failed


def run_build_bronze(args: argparse.Namespace, settings: Settings) -> int:
    """
    Run `build-bronze`; return the number of failed raw objects.
    """
    return _build_bronze(args, settings).failed


def run_ingest(args: argparse.Namespace, settings: Settings) -> int:
    """
    Run `fetch`, then `build-bronze`; return the total number of failures.
    """
    return _fetch(args, settings).failed + _build_bronze(args, settings).failed


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Add the three commands to the parser.
    """
    commands = (
        ("fetch", "FIRMS API -> raw (skips windows already fetched)", run_fetch, True),
        ("build-bronze", "raw -> bronze (skips raw objects already built)", run_build_bronze, False),
        ("ingest", "fetch, then build bronze", run_ingest, True),
    )
    for name, text, handler, has_force in commands:
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("--source", required=True)
        cmd.add_argument("--start", "--date", dest="start", type=date.fromisoformat, required=True)
        cmd.add_argument("--end", type=date.fromisoformat)
        if has_force:
            cmd.add_argument("--force", action="store_true", help="fetch again even if the window was already fetched")
        cmd.set_defaults(run=handler)
