"""Unit test for the #763 JSON extension of check_usb_topology.py.

The PowerShell PnP enumeration is Windows-only; ``get_all_usb_devices`` is
monkeypatched so the test is portable and deterministic and asserts only the
*new* behaviour (the OS-tagged envelope), not the pre-existing tree print.
"""

import json

import check_usb_topology as u

_FAKE = [
    {
        "instance_id": "USB\\ROOT",
        "name": "USB xHCI Host Controller",
        "class_name": "USB",
        "parent_id": "ACPI",
        "bus_desc": "",
    },
    {
        "instance_id": "USB\\DEV1",
        "name": "Intel RealSense",
        "class_name": "Camera",
        "parent_id": "USB\\ROOT",
        "bus_desc": "RealSense",
    },
]


def test_json_envelope_emitted(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "get_all_usb_devices", lambda: list(_FAKE))
    out = tmp_path / "usb.json"

    rc = u.main(["--no-tree", "--json", str(out)])

    assert rc == 0
    assert out.exists()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_name"] == "usb_topology"
    assert payload["n_devices"] == 2
    assert payload["verdict"]["category"] == "CAPTURED"
    assert payload["devices"][1]["name"] == "Intel RealSense"
    # The envelope carries the standard machine/identity block.
    assert "hostname" in payload["machine"]


def test_no_devices_is_honest_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(u, "get_all_usb_devices", lambda: [])
    out = tmp_path / "usb.json"

    rc = u.main(["--no-tree", "--json", str(out)])

    assert rc == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["n_devices"] == 0
    assert payload["verdict"]["category"] == "NO_DEVICES"
