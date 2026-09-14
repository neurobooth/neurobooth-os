"""Tests for :class:`neurobooth_os.iout.mock._pacing.Pacer`.

The mocks exist so a hardware-less session produces LSL streams whose shape and
cadence match the real devices. The cadence half was wrong: every mock did its
work and then slept a full period, so the emitted rate was
``1 / (work + period)``. Measured with MockMbient on macOS at a configured
100 Hz, that was 14.06 ms between samples -- 71 Hz. After this change, 9.98 ms
and 100.2 Hz.

The timing assertions here use generous bounds. They are checking that the
deadline arithmetic absorbs work rather than adding it, which is a large
effect, not that the scheduler is precise, which it is not.
"""

import threading
import time

import pytest

from neurobooth_os.iout.mock._pacing import Pacer


class TestPeriod:
    @pytest.mark.parametrize("rate,expected", [(100, 0.01), (50, 0.02), (1, 1.0)])
    def test_period_is_the_reciprocal_of_the_rate(self, rate, expected):
        assert Pacer(rate).period == pytest.approx(expected)

    @pytest.mark.parametrize("rate", [0, -1, None])
    def test_non_positive_rate_means_no_delay(self, rate):
        """Better to spin than to divide by zero inside a device thread."""
        pacer = Pacer(rate)
        assert pacer.period == 0.0
        start = time.perf_counter()
        pacer.wait()
        assert time.perf_counter() - start < 0.05


class TestPacing:
    def test_work_time_is_absorbed_not_added(self):
        """The defect this exists to fix.

        With a 20 ms period and 10 ms of work per iteration, the old
        sleep-a-full-period approach took ~30 ms per iteration. The deadline
        approach takes ~20 ms.
        """
        pacer = Pacer(50)  # 20 ms
        pacer.wait()  # start the clock
        start = time.perf_counter()
        for _ in range(5):
            time.sleep(0.010)  # stand in for pushing an LSL sample
            pacer.wait()
        elapsed = time.perf_counter() - start

        assert elapsed == pytest.approx(0.100, abs=0.035), (
            f"5 ticks at 20 ms should take ~100 ms, took {elapsed*1000:.1f} ms"
        )
        # The point of the fix: nowhere near work + period per iteration.
        assert elapsed < 0.135

    def test_rate_is_close_to_configured_with_no_work(self):
        pacer = Pacer(100)
        pacer.wait()
        start = time.perf_counter()
        for _ in range(20):
            pacer.wait()
        measured = 20 / (time.perf_counter() - start)
        assert measured == pytest.approx(100, rel=0.35)

    def test_overrun_resyncs_rather_than_bursting(self):
        """A stall must not be followed by a flood of catch-up ticks.

        Real hardware does not emit a backlog after a hiccup, and a burst
        would misreport the rate in the other direction.
        """
        pacer = Pacer(100)  # 10 ms
        pacer.wait()
        time.sleep(0.08)  # overrun by ~8 periods

        start = time.perf_counter()
        pacer.wait()
        first = time.perf_counter() - start

        start = time.perf_counter()
        pacer.wait()
        second = time.perf_counter() - start

        assert first < 0.005, "the overrun tick should return immediately"
        assert second == pytest.approx(0.010, abs=0.010), (
            "the tick after an overrun should be a normal period, not a burst"
        )

    def test_clock_starts_on_first_wait_not_construction(self):
        """Setup between constructing the Pacer and entering the loop must not
        be charged against the first tick.

        Two ticks on a fresh Pacer are two whole periods. Had the clock started
        at construction, the 50 ms of setup would have blown five periods, the
        first tick would resync and return immediately, and this would measure
        one period rather than two -- so the bound has to exclude 10 ms instead
        of straddling it.
        """
        pacer = Pacer(100)  # 10 ms
        time.sleep(0.05)  # slow setup, five periods' worth
        start = time.perf_counter()
        pacer.wait()
        pacer.wait()
        assert time.perf_counter() - start == pytest.approx(0.020, abs=0.006)


class TestStopEvent:
    def test_returns_true_while_running(self):
        assert Pacer(1000, threading.Event()).wait() is True

    def test_returns_false_once_set(self):
        event = threading.Event()
        event.set()
        assert Pacer(1, event).wait() is False

    def test_stops_promptly_rather_than_sitting_out_a_period(self):
        """A 1 Hz mock must not take a second to notice it was stopped."""
        event = threading.Event()
        pacer = Pacer(1, event)
        pacer._deadline = time.perf_counter()  # pretend the loop has already ticked

        threading.Timer(0.05, event.set).start()
        start = time.perf_counter()
        result = pacer.wait()
        elapsed = time.perf_counter() - start

        assert result is False
        assert elapsed < 0.5, f"took {elapsed:.3f}s to notice the stop event"

    def test_without_an_event_always_returns_true(self):
        pacer = Pacer(1000)
        assert pacer.wait() is True
        assert pacer.wait() is True
