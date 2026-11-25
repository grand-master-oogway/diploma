"""
Overpasses: consecutive detections of one satellite with no gap longer than `PASS_GAP`.
"""

from datetime import timedelta
from typing import Final

import polars as pl

PASS_GAP: Final = timedelta(minutes=20)
# Rows of the previous UTC day that can still belong to a pass reaching into the next day (a pass lasts a few minutes).
PASS_LOOKBACK: Final = timedelta(minutes=60)


def assign_passes(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add `pass_id` = `<satellite>_<first acq_time of the pass, YYYYMMDDTHHMM>`, keeping the input row order.

    The id depends only on the pass's own rows, so it is stable when later days arrive. To give a pass that crosses
    midnight UTC the same id on both days, pass in the last `PASS_LOOKBACK` of the previous day as well.
    """
    starts_pass = (pl.col("acq_time").diff().over("satellite") > PASS_GAP).fill_null(value=True)
    start = pl.when(starts_pass).then(pl.col("acq_time")).forward_fill().over("satellite")
    return (
        df.with_row_index("_row")
        .sort("satellite", "acq_time", "_row")
        .with_columns(
            pl.concat_str([pl.col("satellite").cast(pl.String), start.dt.strftime("%Y%m%dT%H%M")], separator="_").alias("pass_id")
        )
        .sort("_row")
        .drop("_row")
    )
