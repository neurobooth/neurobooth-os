"""Active Mbient/BLE soak harness for the Win10 -> Win11 decision (#762).

#759 concern #4. The existing ``extras/perf/mbient_*.py`` scripts are
*retrospective* (they read what production already logged). This is a *test*:
it drives the real BLE stack on demand on one ACQ-class booth, hundreds of
connect / stream / reset / reconnect cycles, and emits numbers two operating
systems can be diffed on.

It calls the **production** ``neurobooth_os.iout.mbient.Mbient`` surface
(`connect` -> `start` -> `reset_and_reconnect` -> `close`) so it exercises the
same code paths the GUI does -- it does not fork or re-implement the driver.
LSL and DB messaging are neutralized at the harness boundary (the established
test pattern: ``mbient.DISABLE_LSL = True`` + ``mbient.post_message`` no-op);
``mbient.py`` itself is untouched.

Same conventions as the timing harness (#761): the run JSON is authoritative,
the ``verdict`` is derived *from* the numbers, and the OS comparison is a
separate tool (``mbient_soak_compare.py``) -- a single run only *captures*.
Output uses the shared ``_baseline_common`` envelope and lands in the
configured log dir, not the repo tree.

Honest limits (stated, not buried -- see ``docs/mbient_soak_summary.md``):

* **The iPhone co-runner is synthetic.** #669 (the access violation that
  coincides with Mbient BLE-connect while the iPhone listener runs) is a
  two-subsystem race. Driving the real iPhone in a multi-hour soak would
  spew large video files into the permanent-storage transfer workflow, so
  ``--with-iphone`` runs a synthetic stand-in that reproduces the *contention
  shape* (a continuously blocking-socket listener thread concurrent with
  Mbient BLE) without an iPhone or any video. A clean Win11 ``--with-iphone``
  result is therefore suggestive, not definitive.
* **Negotiated BLE connection parameters are not recorded.** The production
  public surface only exposes the *requested* ``ConnectionParameters``; the
  negotiated interval/latency/timeout would require new native calls in
  ``mbient.py`` (out of scope per #762). Only the requested values are
  emitted, flagged as such.

Usage::

    uv run python extras/perf/mbient_soak.py \\
        [--json ~/mbients.json | --mac AA:BB.. --mac CC:DD.. | --scan] \\
        [--duration-min 120] [--stream-seconds 30] [--with-iphone] \\
        [--mock] [--wer-dumps] [--out PATH] [--no-json] [--stdout] [--strict]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import multiprocessing as mp
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _baseline_common import (
    CollectionError,
    build_envelope,
    collect_bluetooth_radios,
    collect_os_identity,
    os_segment,
    percentile,
    resolved_log_dir,
)

SCHEMA_VERSION = 1
SCHEMA_NAME = "mbient_soak"

# App-log substrings that indicate a BLE disconnect of interest. Counted by a
# logging handler so a soft (non-crash) link drop is still visible per cycle.
_DISCONNECT_MARKERS = (
    "Disconnected Prematurely",
    "Disconnect with status",
    "Disconnected during reset",
    "Disconnect during attempt_reconnect",
)

# Single-run sanity bounds (NOT the OS pass/fail thresholds -- that is
# mbient_soak_compare.py against a locked Win10 baseline). A flag means "a
# human looks", never "fail".
SANITY_MIN_OK_CYCLE_FRACTION = 0.5  # < half the cycles succeeded -> flag
SANITY_DROP_RATE_FLAG = 0.10  # mean per-cycle sample drop-rate > 10% -> flag


# ---------------------------------------------------------------------------
# Pure layer (stdlib only; unit-tested without the neurobooth stack)
# ---------------------------------------------------------------------------


def _stats(values: List[float]) -> Dict[str, Optional[float]]:
    """Mean / SD / p95 / max / n for a list of numbers (population SD).

    Empty input yields ``n=0`` with the rest ``None`` so callers never crash
    on a soak that produced no usable cycles.
    """
    if not values:
        return {"n": 0, "mean": None, "sd": None, "p95": None, "max": None}
    ordered = sorted(values)
    n = len(ordered)
    mean = sum(ordered) / n
    var = sum((v - mean) ** 2 for v in ordered) / n
    return {
        "n": n,
        "mean": mean,
        "sd": var**0.5,
        "p95": percentile(ordered, 95.0),
        "max": ordered[-1],
    }


def summarize_cycles(cycles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce per-cycle soak records to the comparable metric block.

    Pure: no I/O, no globals, no neurobooth imports -- the unit-test seam.

    Args:
        cycles: Per-cycle dicts written by the worker. Recognized keys:
            ``ok`` (bool), ``connect_ms``, ``reset_ms``, ``cycle_wall_s``,
            ``samples``, ``expected_samples``, ``ble_disconnects``,
            ``error`` (str|None).

    Returns:
        ``{n_cycles, n_ok, n_failed, ok_fraction, connect_ms{}, reset_ms{},
        cycle_wall_s{}, drop_rate{}, ble_disconnects_total,
        cycles_with_disconnect, errors[]}``.
    """
    n = len(cycles)
    ok = [c for c in cycles if c.get("ok")]
    connect_ms = [
        float(c["connect_ms"]) for c in cycles if c.get("connect_ms") is not None
    ]
    reset_ms = [float(c["reset_ms"]) for c in cycles if c.get("reset_ms") is not None]
    wall = [
        float(c["cycle_wall_s"]) for c in cycles if c.get("cycle_wall_s") is not None
    ]
    drop_rates: List[float] = []
    for c in cycles:
        exp = c.get("expected_samples")
        got = c.get("samples")
        if exp and got is not None and exp > 0:
            drop_rates.append(max(0.0, 1.0 - (got / exp)))
    disconnects = [int(c.get("ble_disconnects", 0) or 0) for c in cycles]
    errors = sorted({c["error"] for c in cycles if c.get("error")})

    return {
        "n_cycles": n,
        "n_ok": len(ok),
        "n_failed": n - len(ok),
        "ok_fraction": (len(ok) / n) if n else 0.0,
        "connect_ms": _stats(connect_ms),
        "reset_ms": _stats(reset_ms),
        "cycle_wall_s": _stats(wall),
        "drop_rate": _stats(drop_rates),
        "ble_disconnects_total": sum(disconnects),
        "cycles_with_disconnect": sum(1 for d in disconnects if d > 0),
        "errors": errors,
    }


def derive_verdict(metrics: Dict[str, Any], crash: Dict[str, Any]) -> Dict[str, Any]:
    """Honest single-run verdict. Never pass/fail for the OS question.

    Category is ``CRASHED`` if the worker process died on a native fault
    (the dominant Win10 failure mode -- recording it is the whole point),
    else ``CAPTURED`` / ``CAPTURED_WITH_ERRORS``. ``reasons`` always states
    that the regression assessment is a comparison, plus any obviously-bad
    signal that means the run should probably be re-taken before being
    locked as a baseline.
    """
    reasons: List[str] = [
        "Single-run capture. Regression assessment is a comparison: run "
        "extras/perf/mbient_soak_compare.py against the locked Win10 baseline."
    ]
    hints: List[str] = []

    crashed = bool(crash.get("crashed"))
    if crashed:
        reasons.append(
            f"Worker process exited abnormally (exit_code="
            f"{crash.get('exit_code')}, {crash.get('exit_code_hex')}). "
            f"A native fault is the dominant Win10 failure mode -- this is a "
            f"recorded data point, not a harness bug. See crash.dump_paths / "
            f"the faulthandler log."
        )

    n = metrics.get("n_cycles", 0)
    if n == 0:
        reasons.append("No cycles completed -- soak did not run; investigate.")
    else:
        if metrics["ok_fraction"] < SANITY_MIN_OK_CYCLE_FRACTION:
            reasons.append(
                f"Only {metrics['n_ok']}/{n} cycles succeeded "
                f"(< {SANITY_MIN_OK_CYCLE_FRACTION:.0%}); run may be unusable "
                f"as a baseline."
            )
            hints.append("Re-run on an idle ACQ booth with charged devices.")
        drop_mean = metrics.get("drop_rate", {}).get("mean")
        if drop_mean is not None and drop_mean > SANITY_DROP_RATE_FLAG:
            reasons.append(
                f"Mean per-cycle sample drop-rate {drop_mean:.1%} "
                f"> {SANITY_DROP_RATE_FLAG:.0%} sanity bound."
            )

    if crashed:
        category = "CRASHED"
    elif metrics.get("errors") or metrics.get("n_failed"):
        category = "CAPTURED_WITH_ERRORS"
    else:
        category = "CAPTURED"
    return {
        "category": category,
        "reasons": reasons,
        "remediation_hints": sorted(set(hints)),
    }


def classify_exit(exit_code: Optional[int]) -> Dict[str, Any]:
    """Interpret a worker process exit code.

    ``0`` = clean; ``None`` = never returned (joined-out / terminated);
    anything else = abnormal (on Windows a native access violation surfaces
    as ``3221225477`` / ``0xC0000005``).
    """
    if exit_code == 0:
        return {"crashed": False, "exit_code": 0, "exit_code_hex": "0x0"}
    if exit_code is None:
        return {
            "crashed": True,
            "exit_code": None,
            "exit_code_hex": None,
            "note": "worker did not return (timed out or was terminated)",
        }
    return {
        "crashed": True,
        "exit_code": exit_code,
        "exit_code_hex": hex(exit_code & 0xFFFFFFFF),
    }


# ---------------------------------------------------------------------------
# Synthetic iPhone co-runner (the #669 contention shape, no real iPhone)
# ---------------------------------------------------------------------------


class SyntheticIphoneCorunner:
    """Reproduce the #669 contention *shape* without an iPhone or video.

    #669 is a race between Mbient BLE-connect on the main thread and the
    iPhone *listening thread* (a continuous blocking-socket ``recv`` + Python
    packet processing). This stands that mechanism up with a localhost UDP
    socket: a feeder thread emits small datagrams and a listener thread does
    blocking ``recvfrom`` + a trivial parse in a tight loop, competing for
    the GIL / scheduler exactly while the soak does its BLE work.

    It is explicitly an approximation (no video, no real iPhone, no transfer
    workflow); the run JSON records ``iphone_corunner: "synthetic"`` so a
    Win11 result is read with that caveat.
    """

    def __init__(self, rate_hz: int = 200) -> None:
        self._rate_hz = rate_hz
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self.packets_processed = 0

    def start(self) -> None:
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.bind(("127.0.0.1", 0))
        rx.settimeout(0.5)
        addr = rx.getsockname()

        def _listener() -> None:
            while not self._stop.is_set():
                try:
                    data, _ = rx.recvfrom(2048)
                except socket.timeout:
                    continue
                except OSError:
                    break
                # Trivial parse, mirroring iphone.listen() packet handling.
                if data:
                    self.packets_processed += 1
                    _ = len(data).to_bytes(4, "little")
            rx.close()

        def _feeder() -> None:
            tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            period = 1.0 / max(1, self._rate_hz)
            payload = b"\x01" * 256
            while not self._stop.is_set():
                try:
                    tx.sendto(payload, addr)
                except OSError:
                    break
                time.sleep(period)
            tx.close()

        for fn in (_listener, _feeder):
            t = threading.Thread(
                target=fn, name=f"iphone-syn-{fn.__name__}", daemon=True
            )
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=2)


# ---------------------------------------------------------------------------
# Disconnect tally (no production change; counts app-log markers per cycle)
# ---------------------------------------------------------------------------


class _DisconnectTally(logging.Handler):
    """Count BLE-disconnect log lines and tee the app log to a run file."""

    def __init__(self, log_file: Path) -> None:
        super().__init__(level=logging.DEBUG)
        self.count = 0
        self._fh = open(log_file, "a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:  # noqa: BLE001
            return
        if any(m in msg for m in _DISCONNECT_MARKERS):
            self.count += 1
        try:
            self._fh.write(msg + "\n")
            self._fh.flush()
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        finally:
            super().close()


# ---------------------------------------------------------------------------
# Device construction (model_construct: clean, non-forking, no validation)
# ---------------------------------------------------------------------------


def make_device(
    name: str, mac: str, mock: bool, acc_hz: int, gyro_hz: int, data_range: int
) -> Any:
    """Build a production ``Mbient`` (or ``MockMbient``) for one device.

    Uses the canonical ``model_construct`` builder (the pattern in
    ``tests/pytest/test_mock_mbient.py``) so no pydantic validation or
    ``ENV_devices`` config context is needed. neurobooth imports are lazy so
    this module's pure layer imports without the stack.
    """
    from neurobooth_os.iout.stim_param_reader import (
        MbientDeviceArgs,
        MbientSensorArgs,
        MockMbientDeviceArgs,
    )

    acc = MbientSensorArgs.model_construct(
        sensor_id="acc1", sample_rate=acc_hz, data_range=data_range
    )
    gyro = MbientSensorArgs.model_construct(
        sensor_id="gyro1", sample_rate=gyro_hz, data_range=2000
    )
    args_cls = MockMbientDeviceArgs if mock else MbientDeviceArgs
    device_args = args_cls.model_construct(
        ENV_devices={},
        device_id=f"Mbient_{name}_1",
        sensor_ids=["acc1", "gyro1"],
        sensor_array=[acc, gyro],
        mac=mac,
        device_name=name,
        arg_parser=f"iout.stim_param_reader.py::{args_cls.__name__}()",
    )
    if mock:
        from neurobooth_os.iout.mock.mock_mbient import MockMbient

        return MockMbient(device_args)
    from neurobooth_os.iout.mbient import Mbient

    return Mbient(device_args)


def resolve_device_list(
    macs: List[str], json_path: Optional[str], scan: bool, scan_n: int
) -> List[Tuple[str, str]]:
    """Return ``[(name, mac), ...]`` reusing reset_mbients' discovery (DRY).

    ``--mac`` is handled inline (trivial); ``--json`` / ``--scan`` defer to
    ``reset_mbients.discovery_json`` / ``discovery_scan`` so the device-list
    convention stays single-sourced.
    """
    if json_path:
        extras_dir = Path(__file__).resolve().parent.parent
        if str(extras_dir) not in sys.path:
            sys.path.insert(0, str(extras_dir))
        from reset_mbients import discovery_json

        return [(d.name, d.address) for d in discovery_json(json_path)]
    if macs:
        return [(f"CL-{i}", m) for i, m in enumerate(macs)]
    if scan:
        extras_dir = Path(__file__).resolve().parent.parent
        if str(extras_dir) not in sys.path:
            sys.path.insert(0, str(extras_dir))
        from reset_mbients import discovery_scan

        return [
            (d.name, d.address)
            for d in discovery_scan(timeout_sec=10, n_devices=scan_n)
        ]
    raise SystemExit("No devices: pass --json, --mac (repeatable), or --scan.")


# ---------------------------------------------------------------------------
# Worker (runs in a child process; native crash -> parent reads exit code)
# ---------------------------------------------------------------------------


def run_soak_worker(cfg: Dict[str, Any], jsonl_path: str) -> int:
    """Drive the production Mbient loop, writing one JSONL line per cycle.

    Crash-safe by construction: each cycle is flushed to ``jsonl_path`` as it
    completes, so a native fault mid-soak loses only the in-flight cycle and
    the parent still has every prior one. Python-level per-cycle failures are
    caught and recorded (``ok=False``) so a soft error does not abort the
    soak.

    Returns 0 on clean completion. (A native fault never returns -- the
    process dies and the parent classifies the exit code.)
    """
    # Neutralize LSL + DB at the harness boundary (production module
    # untouched) -- the exact pattern tests/pytest/test_mock_mbient.py uses.
    from neurobooth_os.iout import mbient as mbient_mod

    mbient_mod.DISABLE_LSL = True
    mbient_mod.post_message = lambda msg: None

    try:
        from neurobooth_os.log_manager import enable_crash_handler

        enable_crash_handler("MBIENT_SOAK")
    except Exception:  # noqa: BLE001
        pass  # faulthandler is a bonus; the exit code is the primary signal

    tally = _DisconnectTally(Path(cfg["log_file"]))
    app_logger = logging.getLogger("app")
    app_logger.addHandler(tally)
    app_logger.setLevel(logging.DEBUG)

    corunner = None
    if cfg["with_iphone"]:
        corunner = SyntheticIphoneCorunner()
        corunner.start()

    devices = [
        make_device(
            name,
            mac,
            cfg["mock"],
            cfg["acc_hz"],
            cfg["gyro_hz"],
            cfg["data_range"],
        )
        for name, mac in cfg["devices"]
    ]
    stream_s = cfg["stream_seconds"]
    expected = int(stream_s * cfg["acc_hz"])
    deadline = time.time() + cfg["duration_s"]

    out = open(jsonl_path, "a", encoding="utf-8")

    def _write(rec: Dict[str, Any]) -> None:
        out.write(json.dumps(rec, default=str) + "\n")
        out.flush()

    cycle_idx = 0
    try:
        while time.time() < deadline:
            for name, dev in zip([d[0] for d in cfg["devices"]], devices):
                cycle_idx += 1
                disc0 = tally.count
                rec: Dict[str, Any] = {
                    "cycle": cycle_idx,
                    "device": name,
                    "ts": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
                    "ok": False,
                    "error": None,
                    "connect_ms": None,
                    "reset_ms": None,
                    "samples": None,
                    "expected_samples": expected,
                    "ble_disconnects": 0,
                    "cycle_wall_s": None,
                }
                t_cycle = time.perf_counter()
                try:
                    n0 = dev.n_samples_streamed
                    t0 = time.perf_counter()
                    connected = dev.connect()
                    rec["connect_ms"] = (time.perf_counter() - t0) * 1000.0
                    if not connected:
                        rec["error"] = "connect() returned False"
                        _write(rec)
                        continue

                    dev.start(buzz=False)
                    time.sleep(stream_s)
                    rec["samples"] = dev.n_samples_streamed - n0

                    t0 = time.perf_counter()
                    dev.reset_and_reconnect()
                    rec["reset_ms"] = (time.perf_counter() - t0) * 1000.0
                    rec["ok"] = True
                except Exception as exc:  # noqa: BLE001
                    rec["error"] = f"{type(exc).__name__}: {exc}"
                finally:
                    rec["ble_disconnects"] = tally.count - disc0
                    rec["cycle_wall_s"] = time.perf_counter() - t_cycle
                    _write(rec)
                if time.time() >= deadline:
                    break
    finally:
        for dev in devices:
            try:
                dev.close()
            except Exception:  # noqa: BLE001
                pass
        if corunner is not None:
            corunner.stop()
        out.close()
        app_logger.removeHandler(tally)
        tally.close()
    return 0


# ---------------------------------------------------------------------------
# Run context + optional WER minidumps (HKCU, no admin, reversible)
# ---------------------------------------------------------------------------


def _lib_version(name: str) -> Optional[str]:
    """Best-effort installed-version lookup (None if absent)."""
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:  # noqa: BLE001
        return None


def collect_run_context(
    with_iphone: bool, mock: bool
) -> Tuple[Dict[str, Any], List[CollectionError], Dict[str, Any]]:
    """OS identity + BT radio/driver/power + lib versions + run flags.

    Returns ``(machine, errors, context)``.
    """
    machine, errors = collect_os_identity(None)
    radios, bt_errors = collect_bluetooth_radios(include_power=True)
    errors.extend(bt_errors)
    context = {
        "bluetooth": radios,
        "versions": {
            "python": sys.version.split()[0],
            "metawear": _lib_version("metawear"),
            "warble": _lib_version("warble"),
        },
        "iphone_corunner": ("synthetic" if with_iphone else "none"),
        "mock": mock,
        "connection_params_requested": {
            "min_conn_interval": 7.5,
            "max_conn_interval": 7.5,
            "latency": 0,
            "timeout": 6000,
        },
        "connection_params_negotiated": None,
        "connection_params_note": (
            "negotiated BLE parameters are not exposed by the Mbient public "
            "surface; capturing them would require extending mbient.py "
            "(out of scope, #762). Only requested values are recorded."
        ),
    }
    return machine, errors, context


_WER_KEY = r"Software\Microsoft\Windows\Windows Error Reporting\LocalDumps\python.exe"


def enable_wer_localdumps(dump_dir: Path) -> Optional[str]:
    """Opt-in HKCU WER LocalDumps for python.exe (full dumps). Reversible.

    Returns the dump directory on success (so the caller can scan it), or
    ``None`` if the registry write failed (recorded, never fatal). No admin
    rights needed -- HKCU only.
    """
    try:
        import winreg

        dump_dir.mkdir(parents=True, exist_ok=True)
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _WER_KEY)
        with key:
            winreg.SetValueEx(key, "DumpFolder", 0, winreg.REG_EXPAND_SZ, str(dump_dir))
            winreg.SetValueEx(key, "DumpType", 0, winreg.REG_DWORD, 2)  # full
            winreg.SetValueEx(key, "DumpCount", 0, winreg.REG_DWORD, 10)
        return str(dump_dir)
    except Exception:  # noqa: BLE001
        return None


def disable_wer_localdumps() -> None:
    """Remove the HKCU LocalDumps key we created (restore prior state)."""
    try:
        import winreg

        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, _WER_KEY)
    except Exception:  # noqa: BLE001
        pass


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--mac", action="append", default=[], help="Device MAC (repeatable)."
    )
    p.add_argument(
        "--json",
        dest="json_path",
        help="JSON file of {device_name: MAC} (e.g. ~/mbients.json).",
    )
    p.add_argument(
        "--scan",
        action="store_true",
        help="BLE-scan for devices instead of --mac/--json.",
    )
    p.add_argument(
        "--scan-n",
        type=int,
        default=5,
        help="Expected device count when --scan (default 5).",
    )
    p.add_argument(
        "--duration-min",
        type=float,
        default=120.0,
        help="Soak wall-clock duration in minutes (default 120).",
    )
    p.add_argument(
        "--stream-seconds",
        type=float,
        default=30.0,
        help="Stream seconds per cycle before reset (default 30).",
    )
    p.add_argument("--acc-hz", type=int, default=100)
    p.add_argument("--gyro-hz", type=int, default=100)
    p.add_argument("--data-range", type=int, default=8)
    p.add_argument(
        "--with-iphone",
        action="store_true",
        help="Run the synthetic #669 iPhone-contention co-runner.",
    )
    p.add_argument(
        "--mock",
        action="store_true",
        help="Drive MockMbient (no hardware/DB) for dev/CI.",
    )
    p.add_argument(
        "--wer-dumps",
        action="store_true",
        help="Opt-in HKCU WER full minidumps for python.exe.",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Output JSON path (default: "
        "<log_dir>/mbient_soak/<os>/<host>_<ts>.json).",
    )
    p.add_argument(
        "--no-json",
        action="store_true",
        help="Do not write the JSON file (stdout/console only).",
    )
    p.add_argument(
        "--stdout", action="store_true", help="Also print the JSON envelope to stdout."
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if the worker crashed (CI gate).",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    devices = resolve_device_list(args.mac, args.json_path, args.scan, args.scan_n)

    machine, errors, run_context = collect_run_context(args.with_iphone, args.mock)
    seg = os_segment(machine)
    host = machine.get("hostname", "unknown")
    stamp = dt.datetime.now(tz=dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    out_path = args.out or (
        resolved_log_dir("mbient_soak") / seg / f"{host}_{stamp}.json"
    )
    run_dir = out_path.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / f"{host}_{stamp}.cycles.jsonl"
    log_file = run_dir / f"{host}_{stamp}.app.log"

    dump_dir: Optional[str] = None
    if args.wer_dumps:
        dump_dir = enable_wer_localdumps(run_dir / "dumps")
        if dump_dir is None:
            errors.append(
                CollectionError("crash.wer_dumps", "HKCU LocalDumps set failed")
            )

    cfg: Dict[str, Any] = {
        "devices": devices,
        "duration_s": args.duration_min * 60.0,
        "stream_seconds": args.stream_seconds,
        "acc_hz": args.acc_hz,
        "gyro_hz": args.gyro_hz,
        "data_range": args.data_range,
        "with_iphone": args.with_iphone,
        "mock": args.mock,
        "log_file": str(log_file),
    }

    print(
        f"Mbient soak: {len(devices)} device(s), "
        f"{args.duration_min} min, mock={args.mock}, "
        f"with_iphone={args.with_iphone}",
        file=sys.stderr,
    )

    proc = mp.Process(target=run_soak_worker, args=(cfg, str(jsonl_path)))
    proc.start()
    grace_s = max(60.0, args.stream_seconds * 4)
    proc.join(timeout=args.duration_min * 60.0 + grace_s)
    if proc.is_alive():
        proc.terminate()
        proc.join(timeout=30)
    exit_code = proc.exitcode

    if args.wer_dumps:
        disable_wer_localdumps()

    cycles: List[Dict[str, Any]] = []
    if jsonl_path.exists():
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    cycles.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # a torn final line after a native fault

    crash = classify_exit(exit_code)
    if dump_dir and Path(dump_dir).is_dir():
        crash["dump_paths"] = [str(p) for p in Path(dump_dir).glob("*.dmp")]
    crash["faulthandler_log"] = "neurobooth_crash.log (in the configured log dir)"
    crash["cycles_jsonl"] = str(jsonl_path)
    crash["app_log"] = str(log_file)

    metrics = summarize_cycles(cycles)
    verdict = derive_verdict(metrics, crash)
    payload = build_envelope(
        schema_name=SCHEMA_NAME,
        schema_version=SCHEMA_VERSION,
        machine=machine,
        blocks={"metrics": metrics, "run": run_context, "crash": crash},
        verdict=verdict,
        errors=errors,
    )

    if not args.no_json:
        out_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        print(f"Wrote: {out_path}", file=sys.stderr)
    print(f"Verdict: {verdict['category']}", file=sys.stderr)
    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    if args.strict and crash.get("crashed"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
