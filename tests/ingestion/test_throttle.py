"""
Tests for the MAP_KEY transaction budget (fake clock, no real waiting).
"""

import pytest

from firms_ua.ingestion.throttle import TransactionBudget, request_cost


class FakeTime:
    """
    A clock that only moves when `sleep` is called.
    """

    def __init__(self) -> None:
        """
        Start at zero with no sleeps.
        """
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        """
        Return the current fake time.
        """
        return self.now

    def sleep(self, seconds: float) -> None:
        """
        Advance the fake time.
        """
        self.sleeps.append(seconds)
        self.now += seconds


def test_request_cost_is_two_per_day() -> None:
    """
    The cost follows the probe: 2 transactions per requested day.
    """
    assert request_cost(1) == 2
    assert request_cost(5) == 10


def test_no_wait_while_under_the_limit() -> None:
    """
    Requests that fit the budget never sleep.
    """
    t = FakeTime()
    budget = TransactionBudget(30, 600, clock=t.clock, sleep=t.sleep)
    for _ in range(3):
        budget.acquire(10)
    assert t.sleeps == []
    assert budget.used() == 30


def test_waits_until_the_oldest_entry_expires() -> None:
    """
    A request over the limit waits only until enough old transactions leave the period.
    """
    t = FakeTime()
    budget = TransactionBudget(20, 600, clock=t.clock, sleep=t.sleep)
    budget.acquire(10)
    t.now = 100.0
    budget.acquire(10)
    budget.acquire(10)  # must wait for the first entry (at t=0) to leave the window
    assert t.now >= 600.0
    assert t.now < 700.0
    assert budget.used() == 20


def test_rejects_a_request_larger_than_the_limit() -> None:
    """
    A request that could never fit raises instead of waiting forever.
    """
    t = FakeTime()
    budget = TransactionBudget(5, 600, clock=t.clock, sleep=t.sleep)
    with pytest.raises(ValueError, match="exceeds"):
        budget.acquire(10)
