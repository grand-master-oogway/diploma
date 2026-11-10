"""
Base class for every Parquet table: pandera validation, versioning and Hive partitioning.
"""

import io
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import pandera.polars as pa
import polars as pl
from pandera.errors import SchemaErrors

from firms_ua.errors import SchemaError
from firms_ua.storage import Storage


class ParquetTable(pa.DataFrameModel):
    """
    Parent of all table definitions.

    A subclass declares columns as annotated attributes (Polars dtypes) and, in `Config`:

    - `name`: `"<layer>.<table>"`, for example `"bronze.firms_viirs"`
    - `metadata`: `{"version": <int>, "partition_by": (<column>, ...)}`. Bump `version` when the columns change (data
      then goes to a new `v<N>` folder). Partition columns are stored in folder names, not in the files.
      (Pandera turns unknown `Config` attributes into checks, so these two live inside its `metadata` dict.)

    Validation is strict: unexpected columns, a different column order, wrong dtypes and nulls in non-nullable columns
    are errors. Columns are non-nullable unless declared with `nullable=True`.

    Layout inside the layer's storage: `<table>/v<version>/<key>=<value>/.../part-<UTC timestamp>.parquet`.
    """

    class Config:
        """
        Settings inherited by every table.
        """

        strict = True
        ordered = True

    @classmethod
    def _setting(cls, key: str) -> Any:  # noqa: ANN401
        settings = {"name": getattr(cls.__config__, "name", None), **(getattr(cls.__config__, "metadata", None) or {})}
        value = settings.get(key)
        if value is None:
            where = "Config.name" if key == "name" else f"Config.metadata['{key}']"
            msg = f"{cls.__name__} must define {where}"
            raise TypeError(msg)
        return value

    @classmethod
    def table_name(cls) -> str:
        """
        Return the full table name, `<layer>.<table>`.
        """
        return str(cls._setting("name"))

    @classmethod
    def table_layer(cls) -> str:
        """
        Return the medallion layer from the table name.
        """
        return cls.table_name().split(".", 1)[0]

    @classmethod
    def table_version(cls) -> int:
        """
        Return the table version.
        """
        return int(cls._setting("version"))

    @classmethod
    def partition_columns(cls) -> list[str]:
        """
        Return the Hive partition columns in partition order.
        """
        return list(cls._setting("partition_by"))

    @classmethod
    def column_names(cls) -> list[str]:
        """
        Return all column names in declared order, partition columns included.
        """
        return list(cls.to_schema().columns)

    @classmethod
    def file_columns(cls) -> list[str]:
        """
        Return the columns stored inside the files (all columns except the partitions).
        """
        parts = set(cls.partition_columns())
        return [c for c in cls.column_names() if c not in parts]

    @classmethod
    def polars_schema(cls) -> pl.Schema:
        """
        Return the declared Polars schema of the full table.
        """
        return pl.Schema({name: col.dtype.type for name, col in cls.to_schema().columns.items()})

    @classmethod
    def columns_with_metadata(cls, key: str) -> list[str]:
        """
        Return columns whose `Field(metadata=...)` has a truthy `key`, in declared order.
        """
        return [name for name, col in cls.to_schema().columns.items() if (col.metadata or {}).get(key)]

    @classmethod
    def dataset_prefix(cls) -> str:
        """
        Return the versioned folder of this table inside its layer's storage (no trailing slash).
        """
        return f"{cls.table_name().split('.', 1)[1]}/v{cls.table_version()}"

    @classmethod
    def check(cls, df: pl.DataFrame) -> None:
        """
        Validate `df` (all columns, partitions included) and report every problem at once.

        Raises:
            SchemaError: With one entry per mismatch.
        """
        try:
            cls.validate(df, lazy=True)
        except SchemaErrors as e:
            problems = [item["error"] for group in e.message.values() for items in group.values() for item in items]
            msg = f"{cls.table_name()} schema mismatch: " + "; ".join(problems)
            raise SchemaError(msg) from None

    @staticmethod
    def _part_name(requested_at: datetime) -> str:
        return f"part-{requested_at:%Y%m%dT%H%M%S%fZ}.parquet"

    @classmethod
    def _part_key(cls, partition_values: Mapping[str, object], requested_at: datetime) -> str:
        folders = "/".join(f"{k}={partition_values[k]}" for k in cls.partition_columns())
        return f"{cls.dataset_prefix()}/{folders}/{cls._part_name(requested_at)}"

    @classmethod
    def write(
        cls,
        df: pl.DataFrame,
        store: Storage,
        requested_at: datetime,
        *,
        partition_values: Mapping[str, object] | None = None,
    ) -> list[str]:
        """
        Validate `df` and write one new file per Hive partition; existing files are never touched.

        Args:
            df: Full table frame, partition columns included.
            store: Storage of this table's layer.
            requested_at: Used for the unique file name.
            partition_values: Partition values to use when `df` has no rows (an empty frame carries no keys).

        Returns:
            Keys of the files written.

        Raises:
            SchemaError: If `df` does not match the definition (nothing is written).
            ValueError: If `df` is empty and `partition_values` is missing.
            FileExistsError: If a file with the same key already exists.
        """
        cls.check(df)
        keys = cls.partition_columns()
        if df.height:
            groups = df.partition_by(*keys, as_dict=True)
        elif partition_values is not None:
            groups = {tuple(partition_values[k] for k in keys): df}
        else:
            msg = f"{cls.table_name()}: an empty frame needs partition_values"
            raise ValueError(msg)

        metadata = {"table": cls.table_name(), "version": str(cls.table_version())}
        written: list[str] = []
        for values, group in groups.items():
            key = cls._part_key(dict(zip(keys, values, strict=True)), requested_at)
            buffer = io.BytesIO()
            group.select(cls.file_columns()).write_parquet(buffer, compression="zstd", metadata=metadata)
            store.put_new(key, buffer.getvalue())
            written.append(key)
        return written

    @classmethod
    def part_exists(cls, store: Storage, partition_values: Mapping[str, object], requested_at: datetime) -> bool:
        """
        True if `write(..., requested_at)` already wrote a file under these partition values.

        `partition_values` may name only the leading partition columns (for example just `source`), which finds the
        file in any partition below them.

        Raises:
            ValueError: If `partition_values` is not a leading subset of the partition columns.
        """
        keys = cls.partition_columns()
        given = [k for k in keys if k in partition_values]
        if given != keys[: len(given)] or len(given) != len(partition_values):
            msg = f"partition_values must be a leading subset of {keys}, got {list(partition_values)}"
            raise ValueError(msg)
        folder = "/".join([cls.dataset_prefix(), *(f"{k}={partition_values[k]}" for k in given)])
        suffix = f"/{cls._part_name(requested_at)}"
        return any(key.endswith(suffix) for key in store.list_keys(f"{folder}/"))

    @classmethod
    def has_files(cls, store: Storage) -> bool:
        """
        True if the table has at least one data file.
        """
        return any(k.endswith(".parquet") for k in store.list_keys(f"{cls.dataset_prefix()}/"))

    @classmethod
    def scan_dataset(cls, store: Storage) -> pl.LazyFrame:
        """
        Lazily read the whole table with partition columns restored from the folder names.

        Raises:
            FileNotFoundError: If the table has no files yet.
        """
        if not cls.has_files(store):
            msg = f"{cls.table_name()} v{cls.table_version()} has no files"
            raise FileNotFoundError(msg)
        schema = cls.polars_schema()
        hive_schema = pl.Schema({c: schema[c] for c in cls.partition_columns()})
        lf = pl.scan_parquet(
            store.uri(f"{cls.dataset_prefix()}/**/part-*.parquet"),
            hive_partitioning=True,
            hive_schema=hive_schema,
            **store.polars_options(),
        )
        return lf.select(cls.column_names())

    @classmethod
    def file_version(cls, store: Storage, key: str) -> int:
        """
        Return the table version stored in a data file's Parquet metadata.
        """
        return int(pl.read_parquet_metadata(io.BytesIO(store.get(key)))["version"])
