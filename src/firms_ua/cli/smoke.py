"""
The `smoke` command: check the key, FIRMS access and bucket access of the current identity (run it on a new VM).
"""

import argparse

from firms_ua.common.settings import Settings
from firms_ua.firms_api.client import fetch_availability
from firms_ua.ops.smoke import run_smoke
from firms_ua.storage.factory import open_storage

DEFAULT_CHECKS = ["raw:rw", "bronze:w"]  # what the ingestion identity should be able to do


def run(args: argparse.Namespace, settings: Settings) -> int:
    """
    Run the checks, print one line per check and return the number of failed checks.
    """
    checks = [tuple(item.split(":", 1)) for item in (args.check or DEFAULT_CHECKS)]
    results = run_smoke(
        get_key=settings.get_map_key,
        get_availability=lambda key: fetch_availability(key, timeout=settings.request_timeout_s),
        open_layer=lambda layer: open_storage(settings.storage_root, layer, settings.gcp_project),
        checks=checks,
    )
    for result in results:
        print(f"{'PASS' if result.ok else 'FAIL'}  {result.name}: {result.detail}")  # noqa: T201
    return sum(not r.ok for r in results)


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Add the command to the parser.
    """
    cmd = sub.add_parser("smoke", help="check key, FIRMS and bucket access of the current identity")
    cmd.add_argument(
        "--check",
        action="append",
        metavar="LAYER:MODE",
        help="layer and mode (rw = write then read, w = write only); default: raw:rw bronze:w (the ingestion identity)",
    )
    cmd.set_defaults(run=run)
