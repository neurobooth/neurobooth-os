# -*- coding: utf-8 -*-
"""A fixed-rate clock for the mock devices' synthetic sample threads.

Every mock used to pace itself by doing its work and then sleeping for a full
period::

    while not stop.is_set():
        emit_a_sample()          # takes W seconds
        stop.wait(1.0 / rate)    # sleeps a whole period on top of W

The emitted rate is then ``1 / (W + period + scheduler overhead)``, which is
always below the configured rate and drifts further the higher that rate is.
Measured on macOS with ``MockMbient`` at a configured 100 Hz: a median
inter-sample interval of 14.06 ms, so 71 Hz. Pushing an LSL sample is not free,
and neither is waking a thread.

That matters because the mocks exist so that "the LSL stream shape and cadence
match the real device". The shape did; the cadence did not, and anything using
a mocked session to check throughput or timing was reading a number about 30%
low. The per-mock unit tests did not catch it because they allow generous slack
for scheduling jitter.

:class:`Pacer` measures from a deadline that advances by exactly one period per
iteration, so the work time is absorbed rather than added.
"""

import time
from typing import Optional


class Pacer:
    """Pace a loop at a fixed rate, absorbing the cost of each iteration.

    Args:
        rate_hz: Target rate. Values at or below zero are treated as "as fast
            as the loop will go", which yields no delay at all.
        stop_event: Optional :class:`threading.Event`. When supplied,
            :meth:`wait` returns ``False`` as soon as it is set, so a loop can
            use the return value as its condition and stop promptly instead of
            sitting out a full period first.
    """

    def __init__(self, rate_hz: float, stop_event=None) -> None:
        self.period: float = 1.0 / float(rate_hz) if rate_hz and rate_hz > 0 else 0.0
        self._stop_event = stop_event
        self._deadline: Optional[float] = None

    def wait(self) -> bool:
        """Sleep until the next scheduled tick.

        Returns:
            ``False`` if the stop event fired during the wait, ``True``
            otherwise. Always ``True`` when no stop event was supplied.
        """
        now = time.monotonic()
        if self._deadline is None:
            # First call: the clock starts when the loop starts, not when the
            # Pacer was constructed, so setup time is not charged to tick one.
            self._deadline = now

        self._deadline += self.period
        remaining = self._deadline - now

        if remaining <= 0:
            # The iteration overran its budget. Resync rather than firing the
            # backlog immediately: a burst of catch-up samples would misreport
            # the rate in the other direction and is not what real hardware
            # does after a stall.
            self._deadline = now
            remaining = 0.0

        if self._stop_event is not None:
            return not self._stop_event.wait(remaining)
        if remaining:
            time.sleep(remaining)
        return True
