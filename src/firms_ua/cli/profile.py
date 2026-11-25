"""
The `profile-bronze` command: read-only statistics of bronze that set silver's label tables, checks and thresholds.
"""

import argparse
import json
from datetime import date

import polars as pl

from firms_ua.common.settings import Settings
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.ops.bronze_profile import profile
from firms_ua.storage.factory import open_storage


def run(args: argparse.Namespace, settings: Settings) -> int:
    """
    Profile bronze (optionally one date range) and print the result as JSON.
    """
    bronze = FirmsBronze.scan_dataset(open_storage(settings.storage_root, "bronze", settings.gcp_project))
    day = pl.col("acq_date").str.to_date("%Y-%m-%d")
    if args.start:
        bronze = bronze.filter(day >= args.start)
    if args.end:
        bronze = bronze.filter(day <= args.end)
    print(json.dumps(profile(bronze), indent=2, default=str))  # noqa: T201
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Add the command to the parser.
    """
    parser = sub.add_parser("profile-bronze", help="read-only statistics of bronze for silver's tables and thresholds")
    parser.add_argument("--start", type=date.fromisoformat, help="first acq_date (inclusive)")
    parser.add_argument("--end", type=date.fromisoformat, help="last acq_date (inclusive)")
    parser.set_defaults(run=run)
