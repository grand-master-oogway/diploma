"""
Command line entry points.

- `fetch`: FIRMS API -> raw layer (CSV bytes).
- `build-bronze`: raw layer -> bronze layer (Parquet).
- `ingest`: both steps, for local use.
"""

import argparse
import logging
from datetime import date

from firms_ua.bronze import build_bronze
from firms_ua.firms_client import fetch
from firms_ua.raw import is_fetched, list_raw, write_raw
from firms_ua.settings import Settings
from firms_ua.storage import open_storage
from firms_ua.windows import plan_windows
from logger.config import configure_logging

log = logging.getLogger(__name__)


def _fetch(args: argparse.Namespace, settings: Settings) -> None:
    raw = open_storage(settings.storage_root, "raw", settings.gcp_project)
    for w in plan_windows(args.source, args.start, args.end or args.start, settings.max_day_range):
        if not args.force and is_fetched(raw, w):
            log.info("skip %s %s (+%d days): already in raw", w.source, w.start, w.day_range)
            continue
        log.info("fetch %s %s (+%d days)", w.source, w.start, w.day_range)
        resp = fetch(
            settings.map_key.get_secret_value(), w, settings.bbox,
            timeout=settings.request_timeout_s, max_retries=settings.max_retries,
        )  # fmt: skip
        obj = write_raw(raw, w, resp.content)
        log.info("raw written: %s rows=%d", obj.key, resp.row_count)


def _build_bronze(args: argparse.Namespace, settings: Settings) -> None:
    raw = open_storage(settings.storage_root, "raw", settings.gcp_project)
    bronze = open_storage(settings.storage_root, "bronze", settings.gcp_project)
    objects = list_raw(raw, args.source, args.start, args.end or args.start)
    if not objects:
        log.warning("no raw objects for %s in the requested range", args.source)
    for obj in objects:
        build_bronze(raw, bronze, obj)


def _run(args: argparse.Namespace) -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    if args.command in ("fetch", "ingest"):
        _fetch(args, settings)
    if args.command in ("build-bronze", "ingest"):
        _build_bronze(args, settings)


def main() -> None:
    """
    CLI entry point.
    """
    parser = argparse.ArgumentParser(prog="firms_ua")
    sub = parser.add_subparsers(dest="command", required=True)
    helps = {
        "fetch": "FIRMS API -> raw",
        "build-bronze": "raw -> bronze (skips raw objects already built)",
        "ingest": "fetch, then build bronze",
    }
    for name, text in helps.items():
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("--source", required=True)
        cmd.add_argument("--start", "--date", dest="start", type=date.fromisoformat, required=True)
        cmd.add_argument("--end", type=date.fromisoformat)
        if name != "build-bronze":
            cmd.add_argument("--force", action="store_true", help="fetch again even if raw has the window")
        cmd.set_defaults(func=_run)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
