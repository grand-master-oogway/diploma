"""
BigQuery external-table definitions derived from `ParquetTable` classes, so BigQuery sees the same types as Polars.

The output (one JSON document per table) is committed under `infra/modules/bigquery/schemas/` and read by Terraform.
Partition columns are not file columns: BigQuery gets them from the Hive folder names through a CUSTOM key spec.
"""

import json
from typing import Any, Final

import polars as pl

from firms_ua.datacatalog_core.parquet_table import ParquetTable

_PARTITION_KEY_TYPES: Final = {pl.String: "STRING", pl.Date: "DATE"}


def bigquery_type(dtype: pl.DataType | type[pl.DataType]) -> str:
    """
    Map a Polars dtype to the BigQuery type BigQuery reads from our Parquet files.

    Parquet unsigned integers (`UINT_32`, `UINT_64`) are read as INT64: fine for H3 ids, which are below 2**63.

    Raises:
        TypeError: For a dtype the tables do not use.
    """
    base = dtype.base_type()
    if base in (pl.String, pl.Enum, pl.Categorical):
        return "STRING"
    if dtype.is_integer():
        return "INT64"
    if dtype.is_float():
        return "FLOAT64"
    if base == pl.Boolean:
        return "BOOL"
    if base == pl.Date:
        return "DATE"
    if base == pl.Datetime:
        return "TIMESTAMP" if getattr(dtype, "time_zone", None) == "UTC" else "DATETIME"
    msg = f"no BigQuery mapping for {dtype}"
    raise TypeError(msg)


def bigquery_schema(table: type[ParquetTable]) -> list[dict[str, str]]:
    """
    Return the BigQuery schema of the table's file columns (partition columns excluded), in declared order.

    Every column is NULLABLE: Polars writes optional Parquet columns, and a REQUIRED field would not match them. The
    real nullability is enforced by the table's own validation when it is written.
    """
    schema = table.polars_schema()
    columns = table.to_schema().columns
    return [
        {
            "name": name,
            "type": bigquery_type(schema[name]),
            "mode": "NULLABLE",
            "description": columns[name].description or "",
        }
        for name in table.file_columns()
    ]


def hive_keys(table: type[ParquetTable]) -> str:
    """
    Return the CUSTOM Hive key spec for BigQuery, e.g. `{source:STRING}/{acq_date:STRING}`.

    Raises:
        TypeError: For a partition dtype without a key type.
    """
    schema = table.polars_schema()
    keys = []
    for name in table.partition_columns():
        key_type = _PARTITION_KEY_TYPES.get(schema[name].base_type())
        if key_type is None:
            msg = f"{table.table_name()}: no Hive key type for {name} ({schema[name]})"
            raise TypeError(msg)
        keys.append(f"{{{name}:{key_type}}}")
    return "/".join(keys)


def external_table_spec(table: type[ParquetTable]) -> dict[str, Any]:
    """
    Return everything Terraform needs for one external table: layer, name, path inside the bucket, Hive keys, schema.
    """
    layer, name = table.table_name().split(".", 1)
    return {
        "layer": layer,
        "table": name,
        "version": table.table_version(),
        "path": table.dataset_prefix(),
        "hive_keys": hive_keys(table),
        "description": " ".join((table.__doc__ or "").split()),
        "schema": bigquery_schema(table),
    }


def spec_json(table: type[ParquetTable]) -> str:
    """
    Return the spec as stable, human-readable JSON (what is committed).
    """
    return json.dumps(external_table_spec(table), indent=2, ensure_ascii=False) + "\n"
