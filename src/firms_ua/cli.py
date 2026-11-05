"""
Command line entry points.
"""

import argparse
import logging
from datetime import date
from pathlib import Path

from firms_ua.bronze import is_ingested, write_bronze
from firms_ua.firms_client import fetch
from firms_ua.settings import Settings
from firms_ua.windows import plan_windows
from logger.config import configure_logging

log = logging.getLogger(__name__)


def _ingest(args: argparse.Namespace) -> None:
    s = Settings()
    configure_logging(s.log_level)
    root = Path(s.storage_root)
    for w in plan_windows(args.source, args.start, args.end or args.start, s.max_day_range):
        if not args.force and is_ingested(root, w):
            log.info("skip %s %s (+%d days): already in bronze", w.source, w.start, w.day_range)
            continue
        log.info("fetch %s %s (+%d days)", w.source, w.start, w.day_range)
        resp = fetch(
            s.map_key.get_secret_value(), w, s.bbox,
            timeout=s.request_timeout_s, max_retries=s.max_retries,
        )  # fmt: skip
        write_bronze(root, w, resp)


def main() -> None:
    """
    CLI entry point.
    """
    p = argparse.ArgumentParser(prog="firms_ua")
    sub = p.add_subparsers(required=True)
    ing = sub.add_parser("ingest", help="fetch raw FIRMS data into bronze")
    ing.add_argument("--source", required=True)
    ing.add_argument("--start", "--date", dest="start", type=date.fromisoformat, required=True)
    ing.add_argument("--end", type=date.fromisoformat)
    ing.add_argument("--force", action="store_true")
    ing.set_defaults(func=_ingest)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
