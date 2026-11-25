"""
BigQuery external-table specs: type mapping, Hive keys, and the committed files being current.
"""

from pathlib import Path

import polars as pl
import pytest

from firms_ua.cli.bigquery import SPEC_DIR, spec_files
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.datacatalog.silver import FirmsSilver
from firms_ua.datacatalog_core.bigquery import bigquery_schema, bigquery_type, external_table_spec, hive_keys

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("dtype", "expected"),
    [
        (pl.String, "STRING"),
        (pl.Enum(["a", "b"]), "STRING"),
        (pl.Int8, "INT64"),
        (pl.UInt64, "INT64"),
        (pl.UInt32, "INT64"),
        (pl.Float32, "FLOAT64"),
        (pl.Boolean, "BOOL"),
        (pl.Date, "DATE"),
        (pl.Datetime("us", "UTC"), "TIMESTAMP"),
        (pl.Datetime("us"), "DATETIME"),
    ],
)
def test_type_mapping(dtype: pl.DataType, expected: str) -> None:
    """
    Polars dtypes map to the BigQuery types BigQuery reads from the Parquet files.
    """
    assert bigquery_type(dtype) == expected


def test_unmapped_type_fails() -> None:
    """
    A dtype the tables do not use is refused instead of guessed.
    """
    with pytest.raises(TypeError):
        bigquery_type(pl.List(pl.Int64))


def test_partition_columns_are_hive_keys_not_schema_columns() -> None:
    """
    Partition columns appear only in the Hive key spec, in partition order.
    """
    assert hive_keys(FirmsBronze) == "{source:STRING}/{acq_date:STRING}"
    assert hive_keys(FirmsSilver) == "{acq_date:DATE}"
    names = [c["name"] for c in bigquery_schema(FirmsSilver)]
    assert names == FirmsSilver.file_columns()
    assert "acq_date" not in names
    spec = external_table_spec(FirmsSilver)
    assert (spec["layer"], spec["table"], spec["path"]) == ("silver", "firms_detections", "firms_detections/v1")


def test_committed_specs_are_current() -> None:
    """
    The JSON files Terraform reads match the table definitions; run `firms-ua bq-schemas` after changing a table.
    """
    folder = ROOT / SPEC_DIR
    expected = spec_files()
    assert sorted(p.name for p in folder.glob("*.json")) == sorted(expected)
    for name, content in expected.items():
        assert (folder / name).read_bytes().decode("utf-8") == content, f"{name} is stale: run `firms-ua bq-schemas`"
