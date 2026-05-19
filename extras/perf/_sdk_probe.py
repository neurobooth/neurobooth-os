"""Shared device-SDK probe framework for the Win10 -> Win11 decision (#763).

#759 concern #5. The production drivers carry ``_HAS_*`` import guards and
``NB_MOCK_DEVICES`` fallbacks *for running without hardware*. This is the
opposite: a probe must **fail loudly when the vendor SDK is absent** (that is
the signal), never fall back to a mock. Each driver already exposes a uniform
guard -- ``_require_pyspin`` / ``_require_pyrealsense2`` / ``_require_pylink``
(verified) -- so a probe calls that, then the real vendor API.

Import-light: stdlib + ``_baseline_common`` only at module top; every vendor
SDK is imported lazily inside its probe so this module (and its unit tests)
import on a hardware-less dev box. Off-booth every probe degrades to a
recorded ``sdk_absent`` / ``no_device`` / ``error`` status -- never a
fabricated version (Truth Protocol). The pure layer
(:class:`ProbeResult`, :func:`derive_verdict`, :func:`to_envelope`) is fully
unit-tested here; the real hardware pass is booth-only.

EyeLink is intentionally **not** probed here: ``pylink`` is SR-Research
proprietary and unverifiable off-booth, so it is deferred to its own
follow-up rather than shipping unverified vendor calls (see
``docs/win11_vendor_compat.md``).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _baseline_common import (
    CollectionError,
    build_envelope,
    collect_os_identity,
    os_segment,
    ps_json,
    resolved_log_dir,
)

SCHEMA_VERSION = 1


@dataclasses.dataclass
class ProbeResult:
    """One device/SDK probe outcome.

    ``status`` is the headline:

    * ``ok`` -- SDK present, device seen (and, in smoke mode, one
      frame/handshake succeeded).
    * ``sdk_absent`` -- the vendor SDK is not installed (the ``_require_*``
      guard fired). On Win11 this is the first thing to catch.
    * ``no_device`` -- SDK present but no device on the bus/network.
    * ``error`` -- SDK present, device seen, but the probe raised.
    """

    device: str
    sdk: str
    status: str
    sdk_version: Optional[str] = None
    driver_version: Optional[str] = None
    firmware: Optional[str] = None
    serial: Optional[str] = None
    smoke: bool = False
    smoke_ok: Optional[bool] = None
    detail: Optional[str] = None
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def _err(
    device: str,
    sdk: str,
    exc: BaseException,
    *,
    sdk_absent: bool = False,
    smoke: bool = False,
) -> ProbeResult:
    return ProbeResult(
        device=device,
        sdk=sdk,
        status="sdk_absent" if sdk_absent else "error",
        smoke=smoke,
        smoke_ok=False if smoke else None,
        error=f"{type(exc).__name__}: {exc}",
    )


def probe_flir(smoke: bool = False) -> ProbeResult:
    """FLIR / Spinnaker: library version, camera serial+firmware, one frame.

    Mirrors the production acquire path (``PySpin.System.GetInstance`` ->
    ``GetCameras`` -> ``GetBySerial``) without forking ``flir_cam.py``;
    importing it also applies its ``KMP_DUPLICATE_LIB_OK`` workaround, which
    is itself part of what #763 wants measured on Win11.
    """
    try:
        from neurobooth_os.iout.flir_cam import _require_pyspin

        try:
            _require_pyspin()
        except Exception as exc:  # noqa: BLE001  (guard -> SDK absent)
            return _err("FLIR", "PySpin", exc, sdk_absent=True, smoke=smoke)

        import PySpin  # noqa: F401  (real import; guard already passed)

        system = PySpin.System.GetInstance()
        try:
            lib = system.GetLibraryVersion()
            sdk_version = f"{lib.major}.{lib.minor}.{lib.type}.{lib.build}"
            cam_list = system.GetCameras()
            try:
                count = cam_list.GetSize()
                if count == 0:
                    return ProbeResult(
                        "FLIR",
                        "PySpin",
                        "no_device",
                        sdk_version=sdk_version,
                        smoke=smoke,
                        smoke_ok=False if smoke else None,
                        detail="PySpin loaded but GetCameras() == 0",
                    )
                cam = cam_list.GetByIndex(0)
                nodemap = cam.GetTLDeviceNodeMap()
                serial = _flir_node(PySpin, nodemap, "DeviceSerialNumber")
                fw = _flir_node(PySpin, nodemap, "DeviceVersion")
                smoke_ok: Optional[bool] = None
                if smoke:
                    smoke_ok = _flir_one_frame(cam)
                del cam
                return ProbeResult(
                    "FLIR",
                    "PySpin",
                    "ok",
                    sdk_version=sdk_version,
                    firmware=fw,
                    serial=serial,
                    smoke=smoke,
                    smoke_ok=smoke_ok,
                    detail=f"{count} camera(s)",
                )
            finally:
                cam_list.Clear()
        finally:
            system.ReleaseInstance()
    except Exception as exc:  # noqa: BLE001
        return _err("FLIR", "PySpin", exc, smoke=smoke)


def _flir_node(pyspin: Any, nodemap: Any, name: str) -> Optional[str]:
    try:
        node = pyspin.CStringPtr(nodemap.GetNode(name))
        if pyspin.IsAvailable(node) and pyspin.IsReadable(node):
            return node.GetValue()
    except Exception:  # noqa: BLE001
        return None
    return None


def _flir_one_frame(cam: Any) -> bool:
    try:
        cam.Init()
        try:
            cam.BeginAcquisition()
            try:
                img = cam.GetNextImage(2000)
                ok = not img.IsIncomplete()
                img.Release()
                return bool(ok)
            finally:
                cam.EndAcquisition()
        finally:
            cam.DeInit()
    except Exception:  # noqa: BLE001
        return False


def probe_realsense(smoke: bool = False) -> ProbeResult:
    """Intel RealSense: ``pyrealsense2`` version, device serial+firmware, frame."""
    try:
        from neurobooth_os.iout.camera_intel import _require_pyrealsense2

        try:
            _require_pyrealsense2()
        except Exception as exc:  # noqa: BLE001
            return _err("Intel", "pyrealsense2", exc, sdk_absent=True, smoke=smoke)

        import pyrealsense2 as rs

        sdk_version = getattr(rs, "__version__", None)
        ctx = rs.context()
        devices = ctx.query_devices()
        if len(devices) == 0:
            return ProbeResult(
                "Intel",
                "pyrealsense2",
                "no_device",
                sdk_version=sdk_version,
                smoke=smoke,
                smoke_ok=False if smoke else None,
                detail="pyrealsense2 loaded but query_devices() == 0",
            )
        dev = devices[0]
        serial = _rs_info(rs, dev, "serial_number")
        fw = _rs_info(rs, dev, "firmware_version")
        smoke_ok: Optional[bool] = None
        if smoke:
            smoke_ok = _rs_one_frame(rs)
        return ProbeResult(
            "Intel",
            "pyrealsense2",
            "ok",
            sdk_version=sdk_version,
            firmware=fw,
            serial=serial,
            smoke=smoke,
            smoke_ok=smoke_ok,
            detail=f"{len(devices)} device(s)",
        )
    except Exception as exc:  # noqa: BLE001
        return _err("Intel", "pyrealsense2", exc, smoke=smoke)


def _rs_info(rs: Any, dev: Any, name: str) -> Optional[str]:
    try:
        return dev.get_info(getattr(rs.camera_info, name))
    except Exception:  # noqa: BLE001
        return None


def _rs_one_frame(rs: Any) -> bool:
    pipe = rs.pipeline()
    try:
        pipe.start()
        try:
            frames = pipe.wait_for_frames(5000)
            return frames is not None and frames.size() > 0
        finally:
            pipe.stop()
    except Exception:  # noqa: BLE001
        return False


def probe_iphone(smoke: bool = False) -> ProbeResult:
    """iPhone usbmux: device list, and (smoke) a connect+handshake round-trip.

    No vendor SDK guard -- the path is a raw socket against the usbmuxd
    equivalent -- so ``sdk_absent`` never applies; ``no_device`` means
    usbmux saw no iPhone. Smoke does connect+handshake **only** (no
    ``start()``): it must not trigger an iPhone recording, whose video the
    transfer workflow would sweep to permanent storage (the same constraint
    that made #762's iPhone co-runner synthetic).
    """
    try:
        from neurobooth_os.iout.usbmux import USBMux

        mux = USBMux()
        try:
            mux.process(timeout=2.0)
        except Exception:  # noqa: BLE001
            pass  # listing is best-effort; device count is the signal
        n = len(getattr(mux, "devices", []) or [])
        if n == 0:
            return ProbeResult(
                "iPhone",
                "usbmux",
                "no_device",
                smoke=smoke,
                smoke_ok=False if smoke else None,
                detail="usbmux reachable but no device enumerated",
            )
        smoke_ok: Optional[bool] = None
        detail = f"{n} device(s)"
        if smoke:
            smoke_ok, detail = _iphone_handshake()
        return ProbeResult(
            "iPhone",
            "usbmux",
            "ok",
            smoke=smoke,
            smoke_ok=smoke_ok,
            detail=detail,
        )
    except Exception as exc:  # noqa: BLE001
        return _err("iPhone", "usbmux", exc, smoke=smoke)


def _iphone_handshake() -> Tuple[bool, str]:
    """Connect + handshake + immediate close. No recording (no video)."""
    try:
        from neurobooth_os.iout.iphone import IPhone
        from neurobooth_os.iout.stim_param_reader import IPhoneDeviceArgs

        args = IPhoneDeviceArgs.model_construct(
            ENV_devices={},
            device_id="IPhone_probe_1",
            sensor_ids=["iphone1"],
            sensor_array=[],
            device_name="probe",
            arg_parser="iout.stim_param_reader.py::IPhoneDeviceArgs()",
        )
        phone = IPhone(args)
        ok = bool(phone.connect())
        try:
            phone.close()
        except Exception:  # noqa: BLE001
            pass
        return ok, "connect+handshake ok" if ok else "handshake failed"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def probe_webcam(smoke: bool = False) -> ProbeResult:
    """Webcam: OpenCV version + which capture backend cv2 actually used.

    #763 point 5: ``cv2.CAP_DSHOW`` may silently fall through a Win11
    compatibility shim; ``getBackendName()`` is the cheap way to see whether
    the same path is used on Win11 as on Win10.
    """
    try:
        import cv2

        sdk_version = getattr(cv2, "__version__", None)
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        try:
            if not cap.isOpened():
                return ProbeResult(
                    "Webcam",
                    "cv2",
                    "no_device",
                    sdk_version=sdk_version,
                    smoke=smoke,
                    smoke_ok=False if smoke else None,
                    detail="VideoCapture(0, CAP_DSHOW) did not open",
                )
            try:
                backend = cap.getBackendName()
            except Exception:  # noqa: BLE001
                backend = None
            smoke_ok: Optional[bool] = None
            if smoke:
                ok, _frame = cap.read()
                smoke_ok = bool(ok)
            return ProbeResult(
                "Webcam",
                "cv2",
                "ok",
                sdk_version=sdk_version,
                smoke=smoke,
                smoke_ok=smoke_ok,
                detail=f"backend={backend}",
            )
        finally:
            cap.release()
    except Exception as exc:  # noqa: BLE001
        return _err("Webcam", "cv2", exc, smoke=smoke)


# --- host inventory (reuses the proven _baseline_common PowerShell) --------

_GPU_PS = (
    "Get-CimInstance Win32_VideoController | "
    "Select-Object Name, DriverVersion, DriverDate | ConvertTo-Json -Depth 3"
)
_USBCTRL_PS = (
    "Get-CimInstance Win32_USBController | "
    "Select-Object Name, DeviceID, Manufacturer | ConvertTo-Json -Depth 3"
)
_AUDIO_PS = (
    "Get-CimInstance Win32_SoundDevice | "
    "Select-Object Name, Manufacturer, Status | ConvertTo-Json -Depth 3"
)


def _ps_list(script: str) -> List[Dict[str, Any]]:
    info = ps_json(script)
    if info is None:
        return []
    return info if isinstance(info, list) else [info]


def collect_host_inventory() -> Tuple[Dict[str, Any], List[CollectionError]]:
    """GPU / USB-host-controller / audio inventory via PowerShell."""
    out: Dict[str, Any] = {}
    errors: List[CollectionError] = []
    for key, script in (
        ("gpus", _GPU_PS),
        ("usb_controllers", _USBCTRL_PS),
        ("audio_devices", _AUDIO_PS),
    ):
        try:
            out[key] = _ps_list(script)
        except Exception as exc:  # noqa: BLE001
            errors.append(CollectionError.from_exception(f"host.{key}", exc))
            out[key] = []
    return out, errors


def derive_verdict(probes: List[ProbeResult]) -> Dict[str, Any]:
    """Honest capture verdict. Never pass/fail for the OS question.

    ``OK`` only if every probe is ``ok``; otherwise ``DEGRADED`` with the
    specific devices listed. The standing reason says regression is a
    comparison (``sdk_compare.py`` vs the locked Win10 baseline).
    """
    reasons = [
        "Inventory/smoke capture. Regression is a comparison: run "
        "extras/perf/sdk_compare.py against the locked Win10 baseline."
    ]
    bad = [p for p in probes if p.status != "ok"]
    for p in bad:
        reasons.append(
            f"{p.device}/{p.sdk}: {p.status}" + (f" ({p.error})" if p.error else "")
        )
    return {
        "category": "OK" if not bad else "DEGRADED",
        "reasons": reasons,
        "remediation_hints": (
            [
                "Confirm the vendor SDK/driver is installed and the device is "
                "attached; sdk_absent on a booth that should have it is the "
                "headline Win11 risk."
            ]
            if bad
            else []
        ),
    }


def to_envelope(
    schema_name: str,
    probes: List[ProbeResult],
    host: Optional[Dict[str, Any]] = None,
    extra_errors: Optional[List[CollectionError]] = None,
) -> Dict[str, Any]:
    """Assemble the shared baseline envelope for an inventory/smoke run."""
    machine, errors = collect_os_identity(None)
    if extra_errors:
        errors.extend(extra_errors)
    blocks: Dict[str, Any] = {"probes": [p.as_dict() for p in probes]}
    if host is not None:
        blocks["host"] = host
    return build_envelope(
        schema_name=schema_name,
        schema_version=SCHEMA_VERSION,
        machine=machine,
        blocks=blocks,
        verdict=derive_verdict(probes),
        errors=errors,
    )


# Probe registry for the inventory CLI and the per-device smoke CLIs.
PROBES = {
    "flir": probe_flir,
    "realsense": probe_realsense,
    "iphone": probe_iphone,
    "webcam": probe_webcam,
}


def smoke_cli(
    device_key: str, schema_name: str, argv: Optional[List[str]] = None
) -> int:
    """Shared entry point for the per-device ``*_smoke.py`` scripts.

    One probe in *smoke* mode (the smallest end-to-end action: one frame /
    connect+handshake) -> the shared envelope at
    ``<log_dir>/<schema>/<os>/<host>.json``. Single source of truth for the
    CLI so the four ``*_smoke.py`` wrappers stay one line each (DRY).

    Args:
        device_key: A key in :data:`PROBES`.
        schema_name: Envelope ``schema_name`` (e.g. ``"flir_smoke"``).
        argv: Override for testing.

    Returns:
        ``0`` normally; ``1`` with ``--strict`` when the probe is not ``ok``
        or the smoke action failed.
    """
    p = argparse.ArgumentParser(description=f"{device_key} SDK smoke test")
    p.add_argument("--out", type=Path, help="Output path override.")
    p.add_argument("--no-json", action="store_true", help="Do not write the JSON file.")
    p.add_argument(
        "--stdout", action="store_true", help="Also print the JSON envelope to stdout."
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if the probe is not ok / smoke failed.",
    )
    args = p.parse_args(argv)

    probe = PROBES[device_key](smoke=True)
    payload = to_envelope(schema_name, [probe])
    machine = payload["machine"]
    out_path = args.out or (
        resolved_log_dir(schema_name)
        / os_segment(machine)
        / f"{machine.get('hostname', 'unknown')}.json"
    )
    if not args.no_json:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        print(f"Wrote: {out_path}", file=sys.stderr)

    print(
        f"{probe.device}/{probe.sdk}: {probe.status} "
        f"(smoke_ok={probe.smoke_ok})"
        + (f" sdk={probe.sdk_version}" if probe.sdk_version else "")
        + (f" fw={probe.firmware}" if probe.firmware else ""),
        file=sys.stderr,
    )
    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    if args.strict and (probe.status != "ok" or probe.smoke_ok is False):
        return 1
    return 0
