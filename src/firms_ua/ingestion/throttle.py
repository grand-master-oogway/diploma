"""
Client-side budget for the FIRMS MAP_KEY (transactions per sliding time period).

FIRMS allows 5,000 transactions per 10 minutes per key, and a request costs 2 transactions per day requested
(`docs/probe_findings.md`). The budget waits before a request would exceed the limit, instead of reacting to a 429.
It covers one process only, so the Dagster ingestion asset runs in a concurrency pool of size 1.
"""

import logging
from collections import deque
from collections.abc import Callable
from typing import Final

log = logging.getLogger(__name__)

TRANSACTIONS_PER_DAY: Final = 2


def request_cost(day_range: int) -> int:
    """
    Return the transactions one request of `day_range` days costs.
    """
    return TRANSACTIONS_PER_DAY * day_range


class TransactionBudget:
    """
    Sliding-window limiter: at most `limit` transactions in any `period_s` seconds.
    """

    def __init__(self, limit: int, period_s: float, *, clock: Callable[[], float], sleep: Callable[[float], None]) -> None:
        """
        Create an empty budget; `clock` returns monotonic seconds and `sleep` waits (both injected for tests).
        """
        if limit < 1 or period_s <= 0:
            msg = "limit must be >= 1 and period_s > 0"
            raise ValueError(msg)
        self._limit = limit
        self._period_s = period_s
        self._clock = clock
        self._sleep = sleep
        self._spent: deque[tuple[float, int]] = deque()

    def _drop_expired(self, now: float) -> None:
        while self._spent and self._spent[0][0] <= now - self._period_s:
            self._spent.popleft()

    def used(self) -> int:
        """
        Return the transactions spent in the current period.
        """
        self._drop_expired(self._clock())
        return sum(cost for _, cost in self._spent)

    def acquire(self, cost: int) -> None:
        """
        Wait until `cost` transactions fit in the budget, then record them.

        Raises:
            ValueError: If `cost` alone exceeds the limit (it could never fit).
        """
        if cost > self._limit:
            msg = f"a request of {cost} transactions exceeds the limit of {self._limit}"
            raise ValueError(msg)
        while True:
            now = self._clock()
            self._drop_expired(now)
            spent = sum(c for _, c in self._spent)
            if spent + cost <= self._limit:
                self._spent.append((now, cost))
                return
            # Wait until enough of the oldest entries expire.
            freed = 0
            wait_until = now
            for at, c in self._spent:
                freed += c
                wait_until = at + self._period_s
                if spent - freed + cost <= self._limit:
                    break
            delay = max(wait_until - now, 0.0) + 0.01
            log.info("FIRMS budget: %d/%d transactions used, waiting %.0f s", spent, self._limit, delay)
            self._sleep(delay)
