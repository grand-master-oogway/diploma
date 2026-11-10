"""
Typed results of the FIRMS API calls.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class FirmsResponse:
    """
    Raw API response; `content` is unchanged bytes.
    """

    content: bytes
    status: int
    url_redacted: str
    row_count: int


@dataclass(frozen=True)
class Availability:
    """
    The date range FIRMS can serve for one source.
    """

    data_id: str
    min_date: date
    max_date: date


@dataclass(frozen=True)
class KeyStatus:
    """
    Transaction budget of a MAP_KEY: used in the current interval, the limit and the interval length.
    """

    current_transactions: int
    transaction_limit: int
    transaction_interval: str
