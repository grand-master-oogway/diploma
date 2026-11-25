"""
Command line entry point: builds the parser from the command modules and dispatches.

Commands (one module each): `fetch`, `build-bronze`, `ingest` (cli/ingest.py), `probe` (cli/probe.py), `smoke` (cli/smoke.py),
`profile-bronze` (cli/profile.py), `bq-schemas` (cli/bigquery.py).
The exit code is 1 if a command reports failures.
"""

import argparse
import sys

from firms_ua.cli import bigquery, ingest, probe, profile, smoke
from firms_ua.common.settings import Settings
from logger.config import configure_logging


def main() -> None:
    """
    Parse the command line, load the settings, configure logging and run the chosen command.
    """
    parser = argparse.ArgumentParser(prog="firms_ua")
    sub = parser.add_subparsers(dest="command", required=True)
    for module in (ingest, probe, profile, smoke, bigquery):
        module.register(sub)
    args = parser.parse_args()
    settings = Settings()
    configure_logging(settings.log_level)
    failures = args.run(args, settings)
    sys.exit(1 if failures else 0)
