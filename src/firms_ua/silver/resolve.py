"""
Choosing among bronze copies: the latest response, exact repeats, and which product (SP or NRT) to prefer.
"""

import polars as pl


def latest_responses(bronze: pl.DataFrame) -> pl.DataFrame:
    """
    Keep only the rows of the latest response (max `requested_at`) per `source` and `acq_date`.

    A day has several responses only after a forced refetch. Mixing them would duplicate detections, and taking the union
    per detection would keep detections FIRMS removed later, so the whole latest response wins.
    """
    latest = pl.col("requested_at") == pl.col("requested_at").max().over("source", "acq_date")
    return bronze.filter(latest)


def drop_repeats(df: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """
    Drop exact repeats of `detection_id` (same source, position and minute), keeping the first; return the count removed.
    """
    unique = df.unique(subset="detection_id", keep="first", maintain_order=True)
    return unique, df.height - unique.height


def mark_preferred(df: pl.DataFrame) -> pl.DataFrame:
    """
    Add `is_preferred`: per satellite and UTC day, SP rows if that day has any SP, otherwise NRT rows.

    A day-level rule, not pixel matching: NRT and SP do not pair one to one (SP often has about twice the rows), so mixing
    matched SP with unmatched NRT inside one day would double count.
    """
    has_sp = (pl.col("product") == "sp").any().over("satellite", "acq_date")
    return df.with_columns(((pl.col("product") == "sp") | ~has_sp).alias("is_preferred"))
