"""
End-to-end runs of the Dagster ingestion assets with local storage and a fake FIRMS fetcher (no network).
"""

from datetime import date
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
from firms_ua.storage.local import LocalStorage

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
    assert [s.name for s in repo.schedule_defs] == ["forward_fill_schedule"]


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


def test_failed_fetch_fails_the_run(tmp_path: Path) -> None:
    """
    A failed request is logged and fails the run, so bronze does not run on missing raw data.
    """
    result = _run(tmp_path, fail=True)
    assert not result.success
    log = read_log(LocalStorage(tmp_path / "raw"))
    assert log["status"].to_list() == ["failed"]
