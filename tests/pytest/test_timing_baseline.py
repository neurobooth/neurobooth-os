"""Unit tests for extras/perf/timing_baseline.py (the Test C emitter).

Only the pure layer is exercised; the microbench measurement and the
PsychoPy flip probe need the booth scientific stack and are intentionally
not unit-tested (they degrade to recorded collection_errors off-booth).
"""

import numpy as np
import pytest

import timing_baseline as tb


@pytest.mark.parametrize("pct", [0, 25, 50, 90, 95, 99, 100])
def test_percentile_matches_numpy_linear(pct):
    vals = [3.0, 1.0, 4.0, 1.5, 5.0, 9.0, 2.0, 6.0]
    got = tb._percentile(sorted(vals), pct)
    assert got == pytest.approx(float(np.percentile(vals, pct)))


def test_percentile_single_value():
    assert tb._percentile([7.0], 95.0) == 7.0


def test_summarize_errors_against_numpy_reference():
    intervals = {
        "pylsl": [0.0100, 0.0100, 0.0100],
        "wait": [0.0120, 0.0090, 0.0135, 0.0101, 0.0098],
    }
    requested = 0.01
    out = tb.summarize_errors(intervals, requested)

    for name, realized in intervals.items():
        errs = np.abs(np.array(realized) - requested)
        s = out[name]
        assert s["n"] == len(realized)
        assert s["mean"] == pytest.approx(float(errs.mean()))
        assert s["sd"] == pytest.approx(float(errs.std()))  # population, ddof=0
        assert s["p95"] == pytest.approx(float(np.percentile(errs, 95)))
        assert s["p99"] == pytest.approx(float(np.percentile(errs, 99)))
        assert s["max"] == pytest.approx(float(errs.max()))


def test_summarize_errors_empty_primitive():
    out = tb.summarize_errors({"pylsl": []}, 0.01)
    assert out["pylsl"] == {
        "mean": 0.0,
        "sd": 0.0,
        "p95": 0.0,
        "p99": 0.0,
        "max": 0.0,
        "n": 0,
    }


@pytest.mark.parametrize(
    "machine,expected",
    [
        ({"os_build": "19045"}, "win10"),
        ({"os_build": "22631"}, "win11"),
        ({"os_build": "22000"}, "win11"),  # first Win11 build
        ({"os_build": "21999"}, "win10"),  # boundary below
        ({"os_caption": "Microsoft Windows 11 Pro"}, "win11"),
        ({"os_caption": "Microsoft Windows 10 Home"}, "win10"),
        ({"os_build": None, "os_caption": "Acme OS"}, "unknown"),
        ({}, "unknown"),
    ],
)
def test_os_segment(machine, expected):
    assert tb.os_segment(machine) == expected


def test_default_output_path():
    p = tb.default_output_path("win10", "stm").as_posix()
    assert p.endswith("extras/perf/baselines/timing/win10/stm.json")


def test_derive_verdict_clean_run_is_captured():
    metrics = {
        "microbench": {
            "pylsl": {"mean": 2e-5, "max": 5e-5, "n": 100},
        }
    }
    v = tb.derive_verdict(metrics, interval=0.01)
    assert v["category"] == "CAPTURED"
    # The standing reason must always state that a single run is not a verdict.
    assert any("compare_timing.py" in r for r in v["reasons"])
    assert v["remediation_hints"] == []


def test_derive_verdict_flags_contaminated_run():
    # mean error 0.1s is 10x a 0.01s requested interval -> contamination flag.
    metrics = {
        "microbench": {"wait": {"mean": 0.1, "max": 0.2, "n": 100}},
        "_had_errors": True,
    }
    v = tb.derive_verdict(metrics, interval=0.01)
    assert v["category"] == "CAPTURED_WITH_ERRORS"
    assert any("contaminated" in r for r in v["reasons"])
    assert v["remediation_hints"]  # a re-run hint is offered


def test_derive_verdict_ignores_empty_primitive():
    metrics = {"microbench": {"pylsl": {"mean": 0.0, "max": 0.0, "n": 0}}}
    v = tb.derive_verdict(metrics, interval=0.01)
    assert v["category"] == "CAPTURED"
    assert len(v["reasons"]) == 1  # only the standing reason
