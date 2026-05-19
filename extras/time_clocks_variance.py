# -*- coding: utf-8 -*-
"""Per-primitive timing-error microbenchmark (strategy doc "Test C").

Measures the realized vs. requested wait of the five timing primitives the
whole neurobooth timing stack is built on. This is the most
OS-scheduler-sensitive layer and the cheapest signal for the Win10 -> Win11
question (#759 concern #3, issue #761).

Originally a 2022 print-only standalone script. Refactored so the
measurement loop is importable: the JSON metrics emitter
``extras/perf/timing_baseline.py`` calls :func:`measure_primitives`; running
this file directly still prints the per-primitive mean +/- SD error exactly
as the original did, so its standalone use is unchanged.

Created on Wed Apr 27 15:46:36 2022 (@author: STM); refactored for #761.
"""

from __future__ import annotations

import time
from typing import Dict, List

import numpy as np

DEFAULT_INTERVAL = 0.01
DEFAULT_N_REPS = 100
DEFAULT_SETTLE = 1.0

# Stable primitive identifiers. Kept as module-level constants so the
# emitter, the comparator, and the tests all agree on the names.
PRIMITIVES = ("pylsl", "time.time", "time.sleep", "wait", "wait_hogcpuperiod")


def measure_primitives(
    time_period: float = DEFAULT_INTERVAL,
    n_reps: int = DEFAULT_N_REPS,
    settle: float = DEFAULT_SETTLE,
) -> Dict[str, List[float]]:
    """Measure the realized wait duration of each timing primitive.

    For each primitive, request a ``time_period`` wait ``n_reps`` times and
    record the realized interval each time. A short idle ``settle`` between
    primitives keeps one primitive's scheduler/CPU state from biasing the
    next (behaviour preserved from the original script).

    ``psychopy`` and ``pylsl`` are imported lazily inside this function so
    the module can be imported (and unit-tested) on a machine without the
    booth scientific stack; only actually *running* the benchmark needs them.

    Args:
        time_period: Requested wait, in seconds.
        n_reps: Repetitions per primitive.
        settle: Idle seconds between primitives.

    Returns:
        Mapping of primitive name -> list of realized intervals (seconds).
        The caller derives the error as ``realized - time_period``;
        :mod:`timing_baseline` reports absolute-error statistics.
    """
    from psychopy.core import wait
    from pylsl import local_clock

    intervals: Dict[str, List[float]] = {}

    intervals["pylsl"] = []
    for _ in range(n_reps):
        t1 = local_clock()
        t2 = local_clock()
        while t2 - t1 < time_period:
            t2 = local_clock()
        intervals["pylsl"].append(t2 - t1)

    time.sleep(settle)

    intervals["time.time"] = []
    for _ in range(n_reps):
        t1 = time.time()
        t2 = time.time()
        while t2 - t1 < time_period:
            t2 = time.time()
        intervals["time.time"].append(t2 - t1)

    time.sleep(settle)

    intervals["time.sleep"] = []
    for _ in range(n_reps):
        t1 = local_clock()
        time.sleep(time_period)
        t2 = local_clock()
        intervals["time.sleep"].append(t2 - t1)

    time.sleep(settle)

    intervals["wait"] = []
    for _ in range(n_reps):
        t1 = local_clock()
        wait(time_period, hogCPUperiod=0)
        t2 = local_clock()
        intervals["wait"].append(t2 - t1)

    time.sleep(settle)

    intervals["wait_hogcpuperiod"] = []
    for _ in range(n_reps):
        t1 = local_clock()
        wait(time_period, hogCPUperiod=time_period)
        t2 = local_clock()
        intervals["wait_hogcpuperiod"].append(t2 - t1)

    time.sleep(settle)
    return intervals


def main() -> None:
    """Legacy CLI: print mean +/- SD of the per-iteration absolute error."""
    print(f"    sleep period: {DEFAULT_INTERVAL}, n_reps: {DEFAULT_N_REPS}")
    intervals = measure_primitives()
    print("")
    for wait_type, realized in intervals.items():
        err = np.abs(np.array(realized) - DEFAULT_INTERVAL)
        print(f"error for {wait_type}: {err.mean():.8f} +/- {err.std():.8f}")


if __name__ == "__main__":
    main()
