"""Unit tests for extras/perf/mbient_soak.py.

Covers the pure aggregation/verdict layer, the synthetic #669 co-runner, the
``model_construct`` device builder, and an end-to-end **mock** soak worker
(no hardware, no DB, no LSL) so the production-surface drive loop is exercised
without a real BLE device.
"""

import json
import time

import pytest

import mbient_soak as s


# --- pure layer -----------------------------------------------------------


def test_stats_empty_and_nonempty():
    empty = s._stats([])
    assert empty["n"] == 0 and empty["mean"] is None and empty["p95"] is None

    st = s._stats([10.0, 20.0, 30.0, 40.0])
    assert st["n"] == 4
    assert st["mean"] == pytest.approx(25.0)
    assert st["max"] == pytest.approx(40.0)


def test_summarize_cycles_core_math():
    cycles = [
        {
            "ok": True,
            "connect_ms": 100.0,
            "reset_ms": 300.0,
            "cycle_wall_s": 5.0,
            "samples": 95,
            "expected_samples": 100,
            "ble_disconnects": 0,
        },
        {
            "ok": False,
            "connect_ms": 5000.0,
            "reset_ms": None,
            "cycle_wall_s": 6.0,
            "samples": 0,
            "expected_samples": 100,
            "ble_disconnects": 1,
            "error": "connect() returned False",
        },
    ]
    m = s.summarize_cycles(cycles)
    assert m["n_cycles"] == 2
    assert m["n_ok"] == 1
    assert m["n_failed"] == 1
    assert m["ok_fraction"] == pytest.approx(0.5)
    assert m["connect_ms"]["mean"] == pytest.approx(2550.0)
    assert m["drop_rate"]["mean"] == pytest.approx((0.05 + 1.0) / 2)
    assert m["ble_disconnects_total"] == 1
    assert m["cycles_with_disconnect"] == 1
    assert m["errors"] == ["connect() returned False"]


def test_summarize_cycles_empty():
    m = s.summarize_cycles([])
    assert m["n_cycles"] == 0
    assert m["ok_fraction"] == 0.0
    assert m["connect_ms"]["mean"] is None


@pytest.mark.parametrize(
    "code,crashed,hexcode",
    [
        (0, False, "0x0"),
        (None, True, None),
        (3221225477, True, "0xc0000005"),
    ],
)
def test_classify_exit(code, crashed, hexcode):
    c = s.classify_exit(code)
    assert c["crashed"] is crashed
    assert c["exit_code_hex"] == hexcode


def test_derive_verdict_clean_captured():
    m = s.summarize_cycles(
        [
            {
                "ok": True,
                "connect_ms": 100.0,
                "reset_ms": 200.0,
                "samples": 100,
                "expected_samples": 100,
                "cycle_wall_s": 1.0,
            }
        ]
    )
    v = s.derive_verdict(m, {"crashed": False, "exit_code": 0})
    assert v["category"] == "CAPTURED"
    assert any("comparison" in r for r in v["reasons"])


def test_derive_verdict_crashed_is_recorded_not_a_bug():
    m = s.summarize_cycles([{"ok": True, "samples": 1, "expected_samples": 1}])
    v = s.derive_verdict(
        m, {"crashed": True, "exit_code": 3221225477, "exit_code_hex": "0xc0000005"}
    )
    assert v["category"] == "CRASHED"
    assert any("not a harness bug" in r for r in v["reasons"])


def test_derive_verdict_flags_low_ok_fraction():
    cycles = [
        {"ok": False, "error": "x", "samples": 0, "expected_samples": 100}
        for _ in range(10)
    ]
    cycles[0]["ok"] = True
    m = s.summarize_cycles(cycles)
    v = s.derive_verdict(m, {"crashed": False, "exit_code": 0})
    assert v["category"] == "CAPTURED_WITH_ERRORS"
    assert any("cycles succeeded" in r for r in v["reasons"])
    assert v["remediation_hints"]


# --- synthetic #669 co-runner ---------------------------------------------


def test_synthetic_iphone_corunner_processes_packets():
    co = s.SyntheticIphoneCorunner(rate_hz=400)
    co.start()
    try:
        time.sleep(0.4)
    finally:
        co.stop()
    assert co.packets_processed > 0


# --- device builder + device list -----------------------------------------


def test_make_device_mock_builds_without_validation_or_db():
    dev = s.make_device(
        "UnitDev",
        "AA:BB:CC:DD:EE:FF",
        mock=True,
        acc_hz=100,
        gyro_hz=100,
        data_range=8,
    )
    from neurobooth_os.iout.mock.mock_mbient import MockMbient

    assert isinstance(dev, MockMbient)
    assert dev.mac == "AA:BB:CC:DD:EE:FF"


def test_resolve_device_list_mac_inline():
    out = s.resolve_device_list(["AA:BB", "CC:DD"], None, False, 5)
    assert out == [("CL-0", "AA:BB"), ("CL-1", "CC:DD")]


def test_resolve_device_list_requires_a_source():
    with pytest.raises(SystemExit):
        s.resolve_device_list([], None, False, 5)


# --- end-to-end mock soak worker ------------------------------------------


def test_run_soak_worker_end_to_end_mock(tmp_path):
    """Drive the production Mbient public surface through the worker against
    MockMbient: JSONL is written crash-safe and summarizes cleanly."""
    import neurobooth_os.iout.mbient as mb

    saved = (mb.DISABLE_LSL, mb.post_message)  # worker mutates these globally
    jsonl = tmp_path / "c.jsonl"
    cfg = {
        "devices": [("SoakA", "AA:BB:CC:DD:EE:01")],
        "duration_s": 0.05,
        "stream_seconds": 0.15,
        "acc_hz": 100,
        "gyro_hz": 100,
        "data_range": 8,
        "with_iphone": True,  # exercises the synthetic co-runner too
        "mock": True,
        "log_file": str(tmp_path / "a.log"),
    }
    try:
        rc = s.run_soak_worker(cfg, str(jsonl))
    finally:
        mb.DISABLE_LSL, mb.post_message = saved

    assert rc == 0
    assert jsonl.exists()
    recs = [json.loads(ln) for ln in jsonl.read_text().splitlines() if ln.strip()]
    assert len(recs) >= 1
    assert recs[0]["ok"] is True
    assert recs[0]["connect_ms"] is not None
    assert recs[0]["samples"] is not None

    m = s.summarize_cycles(recs)
    assert m["n_cycles"] == len(recs)
    assert m["ok_fraction"] == pytest.approx(1.0)
