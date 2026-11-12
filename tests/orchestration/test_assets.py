"""
End-to-end runs of the Dagster ingestion assets with local storage and a fake FIRMS fetcher (no network).
"""

from datetime import UTC, date, datetime
from pathlib import Path

import dagster as dg
import polars as pl

from firms_ua.common.errors import FirmsError
from firms_ua.common.settings import Settings
from firms_ua.common.windows import Window
from firms_ua.firms_api.models import FirmsResponse
from firms_ua.ingestion.log import read_log
from firms_ua.ingestion.runner import fetch_windows
from firms_ua.orchestration.assets import COMPLETE_CHECK, firms_bronze, firms_raw
from firms_ua.orchestration.definitions import defs
from firms_ua.orchestration.partitions import to_key
from firms_ua.orchestration.resources import Fetcher, FirmsPipeline
from firms_ua.orchestration.schedules import ingest_job, ingest_schedule
from firms_ua.storage.local import LocalStorage

RANGE_START = "dagster/asset_partition_range_start"
HEADER = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"


class FakePipeline(FirmsPipeline):
    """
    Pipeline resource writing to a temporary folder and answering requests without the network.
    """

    root: str
    fail: bool = False

    def settings(self) -> Settings:
        """
        Local settings; no `.env` is read.
        """
        return Settings(_env_file=None, storage_root=self.root, map_key="test-key")  # type: ignore[call-arg]

    def fetcher(self, settings: Settings) -> Fetcher:
        """
        Return one detection on the window's first day, or fail like the client does.
        """

        def run(window: Window) -> FirmsResponse:
            if self.fail:
                raise FirmsError("HTTP 500 for https://example/***", http_status=500)
            row = f"50.1,30.2,330.1,0.4,0.4,{window.start},0007,N20,VIIRS,n,2.0NRT,290.1,1.2,N\n"
            return FirmsResponse((HEADER + row).encode(), 200, "https://example/***", 1)

        return run


PARTITION = to_key(("noaa20", date(2026, 8, 3)))


def _run(tmp_path: Path, *, fail: bool = False) -> dg.ExecuteInProcessResult:
    return dg.materialize(
        [firms_raw, firms_bronze],
        partition_key=PARTITION,
        resources={"pipeline": FakePipeline(root=str(tmp_path), fail=fail)},
        raise_on_error=False,
    )


def test_definitions_load() -> None:
    """
    The code location loads with both assets and the forward-fill schedule.
    """
    repo = defs.get_repository_def()
    assert {k.to_user_string() for k in repo.asset_graph.get_all_asset_keys()} == {"firms_raw", "firms_bronze"}
    assert [s.name for s in repo.schedule_defs] == ["ingest_schedule"]
    assert [s.name for s in repo.sensor_defs] == ["ingestion_automation"]


def test_raw_then_bronze_passes_the_check_and_rerun_skips(tmp_path: Path) -> None:
    """
    One partition goes raw -> bronze with a passing completeness check; a second run fetches nothing.
    """
    result = _run(tmp_path)
    assert result.success
    (check,) = result.get_asset_check_evaluations()
    assert check.check_name == COMPLETE_CHECK
    assert check.passed

    again = _run(tmp_path)
    assert again.success
    raw_meta = again.asset_materializations_for_node("firms_raw")[0].metadata
    assert raw_meta["windows"].value == 0
    assert raw_meta["fetched"].value == 0
    (check,) = again.get_asset_check_evaluations()
    assert check.passed

    log = read_log(LocalStorage(tmp_path / "raw"))
    assert log.filter(log["stage"] == "raw").height == 1


def test_day_inside_an_earlier_window_is_not_fetched_again(tmp_path: Path) -> None:
    """
    A day already fetched in a multi-day window (e.g. by the backfill) is skipped by a later single-day run.
    """
    raw = LocalStorage(tmp_path / "raw")
    fetcher = FakePipeline(root=str(tmp_path)).fetcher(FakePipeline(root=str(tmp_path)).settings())
    fetch_windows(raw, [Window("VIIRS_NOAA20_NRT", date(2026, 8, 1), 5)], fetcher)
    result = _run(tmp_path)
    assert result.success
    assert result.asset_materializations_for_node("firms_raw")[0].metadata["windows"].value == 0
    (check,) = result.get_asset_check_evaluations()
    assert check.passed
    assert read_log(raw).filter(pl.col("stage") == "raw").height == 1


def test_bronze_is_requested_after_raw_for_history_partitions(tmp_path: Path) -> None:
    """
    Materializing an old raw partition makes the automation request the same bronze partition, and only that one.
    """
    instance = dg.DagsterInstance.ephemeral()
    pipeline = FakePipeline(root=str(tmp_path))
    test_defs = dg.Definitions(assets=[firms_raw, firms_bronze], resources={"pipeline": pipeline})
    old = to_key(("noaa20", date(2024, 3, 1)))
    first = dg.evaluate_automation_conditions(defs=test_defs, instance=instance)
    assert first.total_requested == 0
    raw = dg.materialize([firms_raw], partition_key=old, instance=instance, resources={"pipeline": pipeline})
    assert raw.success
    after = dg.evaluate_automation_conditions(defs=test_defs, instance=instance, cursor=first.cursor)
    assert after.get_requested_partitions(firms_bronze.key) == {old}
    assert after.total_requested == 1


def test_schedule_requests_unmaterialized_ranges_and_the_run_covers_them(tmp_path: Path) -> None:
    """
    The schedule asks only for days not materialized yet, and a run with its range tags fetches exactly those days.
    """
    with dg.instance_for_test() as instance:
        _check_schedule(instance, FakePipeline(root=str(tmp_path)))


def _check_schedule(instance: dg.DagsterInstance, pipeline: FakePipeline) -> None:
    done = dg.materialize(
        [firms_raw], partition_key=to_key(("noaa20", date(2026, 11, 9))), instance=instance, resources={"pipeline": pipeline}
    )
    assert done.success
    context = dg.build_schedule_context(instance=instance, scheduled_execution_time=datetime(2026, 11, 11, 6, tzinfo=UTC))
    requests = ingest_schedule(context)
    assert isinstance(requests, list)
    noaa20 = [r for r in requests if r.tags[RANGE_START].endswith("|noaa20")]
    assert len(noaa20) == 2  # history up to 11-08, then 11-10
    assert noaa20[1].tags[RANGE_START] == to_key(("noaa20", date(2026, 11, 10)))

    job = dg.Definitions(assets=[firms_raw], jobs=[ingest_job], resources={"pipeline": pipeline}).resolve_job_def(ingest_job.name)
    result = job.execute_in_process(instance=instance, tags=dict(noaa20[1].tags))
    assert result.success
    assert result.asset_materializations_for_node("firms_raw")[0].metadata["source_days"].value == 1


def test_failed_fetch_fails_the_run(tmp_path: Path) -> None:
    """
    A failed request is logged and fails the run, so bronze does not run on missing raw data.
    """
    result = _run(tmp_path, fail=True)
    assert not result.success
    log = read_log(LocalStorage(tmp_path / "raw"))
    assert log["status"].to_list() == ["failed"]
