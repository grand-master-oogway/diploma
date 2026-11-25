"""
The `bq-schemas` command: write the BigQuery external-table specs that Terraform reads.
"""

import argparse
from pathlib import Path
from typing import Final

from firms_ua.common.settings import Settings
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.datacatalog.silver import FirmsSilver, H3DailyActivity
from firms_ua.datacatalog_core.bigquery import spec_json
from firms_ua.datacatalog_core.parquet_table import ParquetTable

# Tables exposed in BigQuery (raw is CSV and stays out; gold is added when it exists).
BIGQUERY_TABLES: Final[tuple[type[ParquetTable], ...]] = (FirmsBronze, FirmsSilver, H3DailyActivity)
SPEC_DIR: Final = Path("infra/modules/bigquery/schemas")


def spec_files() -> dict[str, str]:
    """
    Return file name -> JSON content for every exposed table.
    """
    return {f"{t.table_name().replace('.', '_')}.json": spec_json(t) for t in BIGQUERY_TABLES}


def run(args: argparse.Namespace, settings: Settings) -> int:  # noqa: ARG001  (same signature as every command)
    """
    Write the specs into `--out` (stale files of removed tables are left for a human to delete).
    """
    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    for name, content in spec_files().items():
        (out / name).write_bytes(content.encode("utf-8"))
        print(f"wrote {out / name}")  # noqa: T201
    return 0


def register(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """
    Add the command to the parser.
    """
    parser = sub.add_parser("bq-schemas", help="write the BigQuery external-table specs read by Terraform")
    parser.add_argument("--out", type=Path, default=SPEC_DIR, help=f"output folder (default {SPEC_DIR})")
    parser.set_defaults(run=run)
