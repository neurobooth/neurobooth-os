"""Unit tests for extras/perf/sdk_compare.py."""

import copy
import json

import pytest

import sdk_compare as sc


def _art(
    status="ok",
    sdkv="3.1.0.0",
    fw="1.5",
    smoke=True,
    osb="19045",
    cap="Microsoft Windows 10 Home",
):
    return {
        "schema_name": "sdk_inventory",
        "schema_version": 1,
        "machine": {"os_caption": cap, "os_build": osb, "hostname": "acq"},
        "probes": [
            {
                "device": "FLIR",
                "sdk": "PySpin",
                "status": status,
                "sdk_version": sdkv,
                "driver_version": None,
                "firmware": fw,
                "serial": "SN1",
                "smoke_ok": smoke,
            }
        ],
    }


def test_identical_is_match_with_raw_values_present():
    b = _art()
    c = sc.build_comparison(b, copy.deepcopy(b))
    assert c["flags"] == []
    assert sc.to_verdict(c)["category"] == "MATCH"
    cell = c["probes"]["FLIR/PySpin"]["sdk_version"]
    assert cell == {"baseline": "3.1.0.0", "pilot": "3.1.0.0", "changed": False}


def test_version_roll_is_flagged():
    c = sc.build_comparison(
        _art(), _art(sdkv="3.2.0.0", osb="22631", cap="Microsoft Windows 11 Pro")
    )
    assert c["probes"]["FLIR/PySpin"]["sdk_version"]["flagged"] is True
    assert sc.to_verdict(c)["category"] == "REVIEW"
    assert c["os_transition"]["to"].startswith("Microsoft Windows 11")
    assert any("rolled" in f for f in c["flags"])


def test_status_regression_is_flagged():
    c = sc.build_comparison(_art(), _art(status="sdk_absent", osb="22631"))
    assert c["probes"]["FLIR/PySpin"]["status"]["flagged"] is True
    assert any("regressed" in f for f in c["flags"])


def test_smoke_pass_then_fail_flagged():
    c = sc.build_comparison(_art(smoke=True), _art(smoke=False))
    assert c["probes"]["FLIR/PySpin"]["smoke_ok"]["flagged"] is True


def test_probe_only_one_side_not_comparable():
    b = _art()
    p = _art()
    p["probes"].append({"device": "Intel", "sdk": "pyrealsense2", "status": "ok"})
    c = sc.build_comparison(b, p)
    assert c["probes"]["Intel/pyrealsense2"]["status"] == "not_comparable"
    assert any("only one artefact" in f for f in c["flags"])


def test_schema_mismatch_flagged_but_compares():
    b = _art()
    bad = copy.deepcopy(b)
    bad["schema_version"] = 2
    c = sc.build_comparison(b, bad)
    assert c["schema"]["compatible"] is False
    assert any("schema mismatch" in f for f in c["flags"])
    assert "FLIR/PySpin" in c["probes"]


def test_verdict_first_reason_is_disclaimer():
    c = sc.build_comparison(_art(), copy.deepcopy(_art()))
    assert "not a\n        failure" not in sc.to_verdict(c)["reasons"][0]
    assert "not a failure" in sc.to_verdict(c)["reasons"][0].lower()


@pytest.fixture
def _isolated_log_dir(tmp_path, monkeypatch):
    import neurobooth_os.config as nb_config

    monkeypatch.setattr(nb_config, "neurobooth_config", None, raising=False)
    monkeypatch.delenv("NB_CONFIG", raising=False)
    monkeypatch.setenv("NB_INSTALL", str(tmp_path))
    return tmp_path


def test_main_strict_and_default_path(tmp_path, _isolated_log_dir):
    b = _art()
    pilot = _art(sdkv="9.9.9.9", osb="22631")  # version roll -> flagged
    bp = tmp_path / "w10.json"
    pp = tmp_path / "w11.json"
    bp.write_text(json.dumps(b), encoding="utf-8")
    pp.write_text(json.dumps(pilot), encoding="utf-8")

    assert sc.main([str(bp), str(pp)]) == 0  # flag is REVIEW, exit 0
    out = _isolated_log_dir / "sdk" / "compare_acq.json"
    assert out.exists()
    assert json.loads(out.read_text())["schema_name"] == "sdk_comparison"

    assert sc.main([str(bp), str(pp), "--strict", "--no-json"]) == 1
    pp.write_text(json.dumps(b), encoding="utf-8")
    assert sc.main([str(bp), str(pp), "--strict", "--no-json"]) == 0
