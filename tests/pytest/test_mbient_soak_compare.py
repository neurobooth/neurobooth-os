"""Unit tests for extras/perf/mbient_soak_compare.py.

Asserts the same hard guarantees as the timing comparator (raw deltas always
present, thresholds overridable, flag != fail) plus the #669-specific rule:
a crash-improvement is only credited when the iPhone co-runner state matched.
"""

import copy
import json

import pytest

import mbient_soak_compare as mc


def _run(
    crashed=False, iphone="synthetic", connect_p95=400.0, drop=0.02, okf=0.98, disc=0
):
    return {
        "schema_name": "mbient_soak",
        "schema_version": 1,
        "machine": {
            "os_caption": "Microsoft Windows 10 Home",
            "os_build": "19045",
            "hostname": "acq",
        },
        "metrics": {
            "connect_ms": {"mean": 200.0, "p95": connect_p95, "n": 50},
            "reset_ms": {"mean": 300.0, "p95": 500.0, "n": 50},
            "drop_rate": {"mean": drop, "max": 0.1},
            "ok_fraction": okf,
            "ble_disconnects_total": disc,
        },
        "run": {"iphone_corunner": iphone},
        "crash": {
            "crashed": crashed,
            "exit_code_hex": "0xc0000005" if crashed else "0x0",
        },
    }


def test_identical_inputs_match_but_every_delta_present():
    b = _run()
    c = mc.build_comparison(b, copy.deepcopy(b))
    assert c["flags"] == []
    assert mc.to_verdict(c)["category"] == "MATCH"
    cell = c["latency"]["connect_ms.mean"]
    assert set(cell) >= {"baseline", "pilot", "delta", "ratio"}
    assert cell["delta"] == 0.0
    assert "flagged" not in cell


def test_p95_regression_flagged_and_overridable():
    b = _run()
    p = _run(connect_p95=900.0)  # ratio 2.25
    flagged = mc.build_comparison(b, p)
    assert flagged["latency"]["connect_ms.p95"]["flagged"] is True
    assert mc.to_verdict(flagged)["category"] == "REVIEW"

    loose = mc.build_comparison(b, p, p95_ratio_limit=3.0)
    assert "flagged" not in loose["latency"]["connect_ms.p95"]
    assert loose["flags"] == []


def test_drop_rate_and_ok_fraction_flags():
    c = mc.build_comparison(_run(), _run(drop=0.20))
    assert c["drop_rate_mean"]["flagged"] is True

    c = mc.build_comparison(_run(), _run(okf=0.80))
    assert c["ok_fraction"]["flagged"] is True


def test_new_ble_disconnects_flagged():
    c = mc.build_comparison(_run(disc=0), _run(disc=7))
    assert c["ble_disconnects_total"]["flagged"] is True
    assert any("disconnects rose" in f for f in c["flags"])


def test_crash_regression_is_flagged():
    c = mc.build_comparison(_run(crashed=False), _run(crashed=True))
    assert c["crash"]["flagged"] is True
    assert any("REGRESSION" in f for f in c["flags"])
    assert mc.to_verdict(c)["category"] == "REVIEW"


def test_669_trap_crash_improved_but_iphone_differs_is_flagged():
    b = _run(crashed=True, iphone="synthetic")
    p = _run(crashed=False, iphone="none")
    c = mc.build_comparison(b, p)
    assert c["crash"]["iphone_corunner_match"] is False
    assert c["crash"]["flagged"] is True
    assert any("measurement trap" in f for f in c["flags"])


def test_crash_improved_with_matching_corunner_is_suggestive_not_flagged():
    c = mc.build_comparison(_run(crashed=True), _run(crashed=False))
    assert c["crash"].get("flagged") is None
    assert "suggestive" in c["crash"]["interpretation"]
    assert c["flags"] == []


def test_schema_mismatch_flagged_but_still_compares():
    b = _run()
    bad = copy.deepcopy(b)
    bad["schema_version"] = 2
    c = mc.build_comparison(b, bad)
    assert c["schema"]["compatible"] is False
    assert any("schema mismatch" in f for f in c["flags"])
    assert "connect_ms.mean" in c["latency"]


def test_verdict_first_reason_is_the_disclaimer():
    c = mc.build_comparison(_run(), copy.deepcopy(_run()))
    reasons = mc.to_verdict(c)["reasons"]
    assert "not a failure" in reasons[0].lower()
    assert "synthetic" in reasons[0].lower()
    assert "not measured facts" in c["thresholds"]["_note"]


@pytest.fixture
def _isolated_log_dir(tmp_path, monkeypatch):
    import neurobooth_os.config as nb_config

    monkeypatch.setattr(nb_config, "neurobooth_config", None, raising=False)
    monkeypatch.delenv("NB_CONFIG", raising=False)
    monkeypatch.setenv("NB_INSTALL", str(tmp_path))
    return tmp_path


def test_main_strict_and_default_path(tmp_path, _isolated_log_dir):
    b = _run()
    pilot = _run(connect_p95=900.0)  # flagged
    bp = tmp_path / "win10.json"
    pp = tmp_path / "win11.json"
    bp.write_text(json.dumps(b), encoding="utf-8")
    pp.write_text(json.dumps(pilot), encoding="utf-8")

    # Default: flag is REVIEW, exit 0; JSON lands in the isolated log dir.
    rc = mc.main([str(bp), str(pp)])
    assert rc == 0
    out = _isolated_log_dir / "mbient_soak" / "compare_acq.json"
    assert out.exists()
    assert json.loads(out.read_text())["schema_name"] == "mbient_soak_comparison"

    # --strict turns the same flag into a hard gate; --no-json writes nothing.
    assert mc.main([str(bp), str(pp), "--strict", "--no-json"]) == 1
    pp.write_text(json.dumps(b), encoding="utf-8")
    assert mc.main([str(bp), str(pp), "--strict", "--no-json"]) == 0
