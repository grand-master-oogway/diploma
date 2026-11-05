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


def _ingest(args: argparse.Namespace) -> None:
    s = Settings()
    root = Path(s.storage_root)
    for w in plan_windows(args.source, args.start, args.end or args.start, s.max_day_range):
        if not args.force and is_ingested(root, w):
            logging.info("skip %s %s (+%d)", w.source, w.start, w.day_range)
            continue
        resp = fetch(
            s.map_key.get_secret_value(), w, s.bbox,
            timeout=s.request_timeout_s, max_retries=s.max_retries,
        )  # fmt: skip
        out = write_bronze(root, w, resp, s.bbox)
        logging.info("wrote %s (%d rows)", out, resp.row_count)


def main() -> None:
    """
    CLI entry point.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
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
