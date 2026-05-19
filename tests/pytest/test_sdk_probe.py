"""Unit tests for extras/perf/_sdk_probe.py and sdk_inventory.py.

The pure layer (ProbeResult / derive_verdict / to_envelope) is tested
directly; the real probes are asserted to **degrade** (never crash, never
fabricate a version) since no vendor SDK / device is present off-booth --
which is exactly the dev-box reality, so this is real coverage.
"""

import json

import pytest

import _sdk_probe as sp


def test_probe_result_as_dict_roundtrip():
    r = sp.ProbeResult("FLIR", "PySpin", "ok", sdk_version="3.1.0.0")
    d = r.as_dict()
    assert d["device"] == "FLIR" and d["status"] == "ok"
    assert d["sdk_version"] == "3.1.0.0"
    assert d["error"] is None


def test_derive_verdict_ok_and_degraded():
    ok = sp.ProbeResult("Webcam", "cv2", "ok")
    bad = sp.ProbeResult("FLIR", "PySpin", "sdk_absent", error="RuntimeError: x")
    assert sp.derive_verdict([ok])["category"] == "OK"
    v = sp.derive_verdict([ok, bad])
    assert v["category"] == "DEGRADED"
    assert any("FLIR/PySpin: sdk_absent" in r for r in v["reasons"])
    assert v["remediation_hints"]


def test_to_envelope_shape():
    env = sp.to_envelope("sdk_inventory", [sp.ProbeResult("X", "y", "ok")])
    assert list(env.keys()) == [
        "schema_version",
        "schema_name",
        "captured_at",
        "machine",
        "probes",
        "verdict",
        "collection_errors",
    ]
    assert env["schema_name"] == "sdk_inventory"
    assert env["probes"][0]["device"] == "X"


@pytest.mark.parametrize("key", list(sp.PROBES))
def test_every_probe_degrades_gracefully_offbooth(key):
    """No SDK/device here -> a recorded status, never a crash or fake version."""
    r = sp.PROBES[key](smoke=False)
    assert r.status in ("ok", "sdk_absent", "no_device", "error")
    if r.status in ("sdk_absent", "no_device", "error"):
        # Must not invent a build it never read.
        assert r.firmware is None and r.serial is None


def test_smoke_cli_strict_semantics(tmp_path, monkeypatch):
    import neurobooth_os.config as nb_config

    monkeypatch.setattr(nb_config, "neurobooth_config", None, raising=False)
    monkeypatch.delenv("NB_CONFIG", raising=False)
    monkeypatch.setenv("NB_INSTALL", str(tmp_path))

    # FLIR SDK is absent off-booth -> --strict must exit non-zero.
    assert sp.smoke_cli("flir", "flir_smoke", ["--no-json", "--strict"]) == 1
    # Default (no --strict) is always 0 -- a capture, not a gate.
    assert sp.smoke_cli("flir", "flir_smoke", ["--no-json"]) == 0
    # Default path lands under the isolated log dir.
    assert sp.smoke_cli("webcam", "webcam_smoke", []) == 0
    out = tmp_path / "webcam_smoke"
    assert out.exists()


def test_sdk_inventory_main_writes_envelope(tmp_path, monkeypatch):
    import neurobooth_os.config as nb_config

    monkeypatch.setattr(nb_config, "neurobooth_config", None, raising=False)
    monkeypatch.delenv("NB_CONFIG", raising=False)
    monkeypatch.setenv("NB_INSTALL", str(tmp_path))

    import sdk_inventory

    rc = sdk_inventory.main([])
    assert rc == 0  # informational; non-OK still exits 0 without --strict
    files = list((tmp_path / "sdk_inventory").rglob("*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["schema_name"] == "sdk_inventory"
    assert {p["device"] for p in payload["probes"]} == {
        "FLIR",
        "Intel",
        "iPhone",
        "Webcam",
    }
