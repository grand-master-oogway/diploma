"""
End-to-end runs of the silver assets on fixture bronze in local storage (no network).
"""

import io
from datetime import UTC, date, datetime
from pathlib import Path

import dagster as dg
import polars as pl

from bronze_factory import bronze
from firms_ua.common.settings import Settings
from firms_ua.datacatalog.bronze import FirmsBronze
from firms_ua.datacatalog.silver import FirmsSilver, H3DailyActivity
from firms_ua.orchestration.resources import FirmsPipeline
from firms_ua.orchestration.silver_assets import firms_h3_activity, firms_silver
from firms_ua.storage.local import LocalStorage

RANGE_START = "dagster/asset_partition_range_start"
RANGE_END = "dagster/asset_partition_range_end"


class LocalPipeline(FirmsPipeline):
    """
    Pipeline resource on a temporary folder; no `.env` is read.
    """

    root: str

    def settings(self) -> Settings:
        """
        Local settings.
        """
        return Settings(_env_file=None, storage_root=self.root)  # type: ignore[call-arg]


def seed_bronze(root: Path, frame: pl.DataFrame) -> None:
    """
    Write a bronze frame into the local bronze storage.
    """
    FirmsBronze.write(frame, LocalStorage(root / "bronze"), datetime(2026, 11, 10, tzinfo=UTC))


def run(root: Path, first: str, last: str) -> dg.ExecuteInProcessResult:
    """
    Materialize both silver assets for the inclusive day range.
    """
    return dg.materialize(
        [firms_h3_activity, firms_silver],
        resources={"pipeline": LocalPipeline(root=str(root))},
        tags={RANGE_START: first, RANGE_END: last},
        raise_on_error=False,
    )


def test_two_days_build_pass_checks_and_rerun_is_identical(tmp_path: Path) -> None:
    """
    Two days build pass checks and rerun is identical.
    """
    seed_bronze(
        tmp_path,
        bronze(
            {"acq_date": "2025-07-14", "acq_time": "2358"},
            {"acq_time": "3"},  # same pass, after midnight
            {"acq_time": "1040", "latitude": "49.9"},
            {"latitude": "53.90", "longitude": "27.56"},  # Minsk: dropped
        ),
    )
    first = run(tmp_path, "2025-07-14", "2025-07-16")
    assert first.success
    silver = LocalStorage(tmp_path / "silver")
    out = FirmsSilver.scan_dataset(silver).sort("acq_time").collect()
    assert out["pass_id"].to_list() == ["noaa20_20250714T2358", "noaa20_20250714T2358", "noaa20_20250715T1040"]
    assert H3DailyActivity.scan_dataset(silver).collect().height == 3
    assert FirmsSilver.part_files(silver, {"acq_date": date(2025, 7, 16)})  # a day with no rows still has a file
    checks = first.get_asset_check_evaluations()
    blocking = [c for c in checks if c.check_name not in {"satellite_gaps", "preferred_jump"}]
    assert blocking and all(c.passed for c in blocking)
    [mat] = [m for m in first.asset_materializations_for_node("firms_silver")][:1]
    assert mat.metadata["dropped_outside_buffer"].value == 1
    key = FirmsSilver.part_files(silver, {"acq_date": date(2025, 7, 15)})[0]
    assert pl.read_parquet_metadata(io.BytesIO(silver.get(key)))["boundary_sha256"]

    second = run(tmp_path, "2025-07-14", "2025-07-16")
    assert second.success
    again = FirmsSilver.scan_dataset(silver).sort("acq_time").collect()
    assert again.drop("run_id").equals(out.drop("run_id"))
    assert all(len(FirmsSilver.part_files(silver, {"acq_date": d})) == 1 for d in (date(2025, 7, 14), date(2025, 7, 15)))


def test_blocking_check_failure_fails_the_run_and_skips_the_day(tmp_path: Path) -> None:
    """
    Blocking check failure fails the run and skips the day.
    """
    seed_bronze(tmp_path, bronze({"frp": "-5"}, {"acq_date": "2025-07-16"}))
    result = run(tmp_path, "2025-07-15", "2025-07-16")
    assert not result.success
    silver = LocalStorage(tmp_path / "silver")
    assert FirmsSilver.part_files(silver, {"acq_date": date(2025, 7, 15)}) == []
    assert len(FirmsSilver.part_files(silver, {"acq_date": date(2025, 7, 16)})) == 1
