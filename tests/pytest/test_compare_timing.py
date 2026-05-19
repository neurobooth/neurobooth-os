"""Unit tests for extras/perf/compare_timing.py.

The strategy doc's hard requirements are asserted explicitly: raw deltas are
always present (even when nothing is flagged), thresholds are overridable,
and a flag is REVIEW (never an auto-fail).
"""

import copy
import json

import pytest

import compare_timing as ct


def _baseline():
    return {
        "schema_name": "timing_baseline",
        "schema_version": 1,
        "machine": {
            "os_caption": "Microsoft Windows 10 Home",
            "os_build": "19045",
            "hostname": "stm",
        },
        "metrics": {
            "requested_interval_s": 0.01,
            "microbench": {
                "pylsl": {
                    "mean": 1e-5,
                    "sd": 2e-6,
                    "p95": 3e-6,
                    "p99": 4e-6,
                    "max": 5e-6,
                    "n": 100,
                },
            },
            "flip_stats": {
                "mean_ms": 16.67,
                "sd_ms": 0.5,
                "p95_ms": 17.0,
                "p99_ms": 17.2,
                "max_ms": 18.0,
                "dropped_flips": 0,
                "requested_hz": 60.0,
                "n": 600,
            },
        },
    }


def test_identical_inputs_match_but_every_delta_present():
    base = _baseline()
    cmp = ct.build_comparison(base, copy.deepcopy(base))
    assert cmp["flags"] == []
    assert ct.to_verdict(cmp)["category"] == "MATCH"

    # Every microbench stat keeps a full raw cell, nothing hidden.
    for stat in ct._MICROBENCH_STATS:
        cell = cmp["microbench"]["pylsl"][stat]
        assert set(cell) >= {"baseline", "pilot", "delta", "ratio"}
        assert cell["delta"] == 0.0
        assert cell["ratio"] == pytest.approx(1.0)
        assert "flagged" not in cell


def test_p99_regression_is_flagged():
    base = _baseline()
    pilot = copy.deepcopy(base)
    pilot["metrics"]["microbench"]["pylsl"]["p99"] = 9e-6  # ratio 2.25 > 2.0
    cmp = ct.build_comparison(base, pilot)
    assert cmp["microbench"]["pylsl"]["p99"]["flagged"] is True
    assert any("p99" in f for f in cmp["flags"])
    assert ct.to_verdict(cmp)["category"] == "REVIEW"


def test_sd_regression_is_flagged_and_threshold_overridable():
    base = _baseline()
    pilot = copy.deepcopy(base)
    pilot["metrics"]["microbench"]["pylsl"]["sd"] = 2.6e-6  # ratio 1.30

    flagged = ct.build_comparison(base, pilot)  # default 1.25
    assert flagged["microbench"]["pylsl"]["sd"]["flagged"] is True

    loosened = ct.build_comparison(base, pilot, sd_ratio_limit=1.5)
    assert "flagged" not in loosened["microbench"]["pylsl"]["sd"]
    assert loosened["flags"] == []


def test_sd_rising_from_zero_baseline_is_flagged():
    base = _baseline()
    base["metrics"]["microbench"]["pylsl"]["sd"] = 0.0
    pilot = copy.deepcopy(base)
    pilot["metrics"]["microbench"]["pylsl"]["sd"] = 1e-6
    cmp = ct.build_comparison(base, pilot)
    assert cmp["microbench"]["pylsl"]["sd"]["flagged"] is True
    assert any("from ~0" in f for f in cmp["flags"])


def test_new_dropped_flips_flagged():
    base = _baseline()
    pilot = copy.deepcopy(base)
    pilot["metrics"]["flip_stats"]["dropped_flips"] = 5
    cmp = ct.build_comparison(base, pilot)
    assert cmp["flip_stats"]["dropped_flips"]["flagged"] is True
    assert any("dropped flips" in f for f in cmp["flags"])


def test_flip_stats_absent_is_not_comparable_not_crash():
    base = _baseline()
    pilot = copy.deepcopy(base)
    pilot["metrics"]["flip_stats"] = None
    cmp = ct.build_comparison(base, pilot)
    assert cmp["flip_stats"]["status"] == "not_comparable"
    assert "pilot" in cmp["flip_stats"]["reason"]
    # microbench still compared fine.
    assert "pylsl" in cmp["microbench"]


def test_schema_mismatch_flagged_but_still_compares():
    base = _baseline()
    pilot = copy.deepcopy(base)
    pilot["schema_version"] = 2
    cmp = ct.build_comparison(base, pilot)
    assert cmp["schema"]["compatible"] is False
    assert any("schema mismatch" in f for f in cmp["flags"])
    assert "pylsl" in cmp["microbench"]  # comparison still happened


def test_verdict_first_reason_is_the_proposal_disclaimer():
    cmp = ct.build_comparison(_baseline(), copy.deepcopy(_baseline()))
    reasons = ct.to_verdict(cmp)["reasons"]
    assert "proposals" in reasons[0].lower()
    assert "not a failure" in reasons[0].lower()


def test_thresholds_block_records_proposal_note():
    cmp = ct.build_comparison(_baseline(), copy.deepcopy(_baseline()))
    assert "not measured facts" in cmp["thresholds"]["_note"]


def test_main_strict_exit_code(tmp_path, capsys):
    base = _baseline()
    pilot = copy.deepcopy(base)
    pilot["metrics"]["microbench"]["pylsl"]["p99"] = 9e-6  # flagged

    bp = tmp_path / "win10.json"
    pp = tmp_path / "win11.json"
    outp = tmp_path / "delta.json"
    bp.write_text(json.dumps(base), encoding="utf-8")
    pp.write_text(json.dumps(pilot), encoding="utf-8")

    # Default: a flag is REVIEW, exit 0.
    rc = ct.main([str(bp), str(pp), "--json", str(outp)])
    assert rc == 0
    assert outp.exists()
    payload = json.loads(outp.read_text(encoding="utf-8"))
    assert payload["schema_name"] == "timing_comparison"
    assert payload["verdict"]["category"] == "REVIEW"

    # --strict: same flag now a hard gate.
    rc_strict = ct.main([str(bp), str(pp), "--strict"])
    assert rc_strict == 1

    # Clean comparison is exit 0 even with --strict.
    pp.write_text(json.dumps(base), encoding="utf-8")
    assert ct.main([str(bp), str(pp), "--strict"]) == 0
