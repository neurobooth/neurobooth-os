"""Shared helpers for booth baseline-snapshot tools.

Single source of truth for the pieces every baseline artefact shares:

* PowerShell invocation and JSON parsing (OS / hardware probes),
* the machine / OS identity block,
* the :class:`CollectionError` accumulator,
* the JSON envelope shape.

Both ``extras/perf/win11_readiness.py`` (Win11 hardware floor, issue #767)
and ``extras/perf/timing_baseline.py`` (timing microbench, issue #761) emit
the same envelope, so the ``baselines/`` tree, the summary docs, and a single
reader/comparator convention stay uniform across artefact kinds.

This module is import-only; it has no ``__main__``. It is loaded the same way
``_db.py`` is -- the perf scripts run from ``extras/perf/`` so a bare
``from _baseline_common import ...`` resolves.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def run_powershell(script: str, timeout: int = 60) -> str:
    """Execute a PowerShell snippet and return its stdout.

    Args:
        script: PowerShell source to run via ``powershell -Command``.
        timeout: Seconds before the call is killed.

    Returns:
        Captured stdout, stripped of trailing whitespace.

    Raises:
        subprocess.CalledProcessError: PowerShell exited non-zero.
        subprocess.TimeoutExpired: ``timeout`` elapsed.
    """
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise subprocess.CalledProcessError(
            completed.returncode,
            "powershell",
            output=completed.stdout,
            stderr=completed.stderr,
        )
    return completed.stdout.strip()


def ps_json(script: str, timeout: int = 60) -> Any:
    """Run a PowerShell snippet that pipes through ``ConvertTo-Json`` and parse it.

    Args:
        script: PowerShell source. The caller is responsible for the
            ``ConvertTo-Json`` pipe; ``-Depth 5`` is recommended.
        timeout: Forwarded to :func:`run_powershell`.

    Returns:
        Parsed JSON value, or ``None`` if PowerShell produced empty output.
    """
    raw = run_powershell(script, timeout=timeout)
    if not raw:
        return None
    return json.loads(raw)


def parse_ps_date(value: Any) -> Any:
    """Convert PowerShell's ``/Date(ms)/`` JSON representation to ISO-8601.

    Returns the input unchanged if it isn't a ``/Date(...)/`` string.
    """
    if not isinstance(value, str) or not value.startswith("/Date("):
        return value
    try:
        ms_token = value.split("(")[1].split(")")[0]
        ms = int(ms_token.split("+")[0].split("-")[0])
        return dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return value


@dataclass
class CollectionError:
    """A single non-fatal failure during data collection."""

    field: str
    message: str

    @classmethod
    def from_exception(cls, where: str, exc: BaseException) -> "CollectionError":
        """Build a :class:`CollectionError` from a caught exception.

        Args:
            where: Dotted path of the field that failed to collect.
            exc: The exception that was trapped.
        """
        return cls(field=where, message=f"{type(exc).__name__}: {exc}")


def collect_os_identity(
    role: Optional[str] = None,
) -> "tuple[dict, list[CollectionError]]":
    """Return the standard ``machine`` block plus any collection errors.

    The block carries hostname, optional booth role, and the OS caption /
    version / build / architecture, matching the ``machine`` object the
    win11_readiness envelope established so one reader convention spans both
    tools. OS identity is best-effort: a PowerShell failure is recorded as a
    :class:`CollectionError` rather than raised, so the caller can still emit
    a useful artefact.

    Args:
        role: Optional booth role (e.g. ``"CTR"``) recorded for triage.

    Returns:
        ``(machine_block, errors)``.
    """
    machine: dict = {"hostname": socket.gethostname()}
    if role:
        machine["role"] = role
    errors: list = []
    try:
        info = ps_json(
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object Caption, Version, BuildNumber, OSArchitecture | "
            "ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            machine["os_caption"] = info.get("Caption")
            machine["os_version"] = info.get("Version")
            machine["os_build"] = info.get("BuildNumber")
            machine["os_arch"] = info.get("OSArchitecture")
    except Exception as exc:  # noqa: BLE001
        errors.append(CollectionError.from_exception("machine.os", exc))
    return machine, errors


def build_envelope(
    *,
    schema_name: str,
    schema_version: int,
    machine: dict,
    blocks: dict,
    verdict: dict,
    errors: "list[CollectionError]",
) -> "dict[str, Any]":
    """Assemble the canonical baseline JSON payload.

    The envelope is intentionally identical in shape to the one
    win11_readiness.py established: ``schema_version``, ``schema_name``,
    ``captured_at`` (UTC ISO-8601), ``machine``, the tool-specific data
    ``blocks`` spread at the top level, ``verdict``, then
    ``collection_errors``. Key order is preserved so committed artefacts
    diff cleanly across tools.

    Args:
        schema_name: Stable identifier for the artefact kind.
        schema_version: Integer bumped on any breaking schema change.
        machine: The machine / OS identity block.
        blocks: Tool-specific top-level keys (e.g. ``{"metrics": {...}}``).
        verdict: ``{"category", "reasons", "remediation_hints"}``.
        errors: Non-fatal collection failures.

    Returns:
        A JSON-serializable dict.
    """
    payload: dict = {
        "schema_version": schema_version,
        "schema_name": schema_name,
        "captured_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "machine": machine,
    }
    payload.update(blocks)
    payload["verdict"] = verdict
    payload["collection_errors"] = [
        {"field": e.field, "message": e.message} for e in errors
    ]
    return payload


def resolved_log_dir(subfolder: Optional[str] = None) -> Path:
    """Return the configured neurobooth log directory (optionally a subfolder).

    Runtime artefacts the timing tools produce belong in the booth's log
    directory, not in the repo working tree. This reuses the project's one
    canonical resolver, ``neurobooth_os.log_manager._get_log_dir`` -- the
    same function the crash/startup logs use -- so the location follows
    ``local_log_dir`` from the loaded neurobooth config, with the project's
    own ``NB_INSTALL`` / home fallback when no config is present.

    Everything is best-effort and import-light: ``neurobooth_os`` is imported
    lazily inside the function so dependency-light tools that only need the
    JSON envelope (``win11_readiness``) never pull the neurobooth stack, and
    a dev box / CI without the package still gets a sane directory. The
    config is loaded (without path validation) only if it has not been
    loaded already, matching the pattern in ``intertask_report.py``; if
    ``NB_CONFIG`` is unset the load is skipped and the fallback applies.

    Args:
        subfolder: Optional child directory appended to the resolved root
            (e.g. ``"timing"``). Not created here; the caller's
            ``mkdir(parents=True)`` does that.

    Returns:
        The resolved directory as a :class:`pathlib.Path`.
    """
    base: Optional[str] = None
    try:
        import neurobooth_os.config as _cfg
        from neurobooth_os.log_manager import _get_log_dir

        if _cfg.neurobooth_config is None:
            try:
                _cfg.load_config(validate_paths=False)
            except Exception:  # noqa: BLE001
                pass  # NB_CONFIG unset / no config file -> use the fallback
        base = _get_log_dir()
    except Exception:  # noqa: BLE001
        base = None  # neurobooth_os not importable (dev box / CI)

    if not base:
        base = os.environ.get("NB_INSTALL") or os.path.expanduser("~")

    root = Path(base)
    return root / subfolder if subfolder else root


def percentile(sorted_vals: "list[float]", pct: float) -> float:
    """Linear-interpolated percentile (numpy 'linear' method), pure-Python.

    Single source of truth for the perf tools' percentile (timing baseline,
    Mbient soak, and the comparators) so the number is computed identically
    everywhere and stays unit-test-stable without the scientific stack.

    Args:
        sorted_vals: Ascending-sorted samples (must be non-empty; callers
            guard the empty case, matching the original timing-baseline use).
        pct: Percentile in [0, 100].

    Returns:
        The interpolated percentile value.
    """
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_vals) - 1)
    frac = rank - low
    return float(sorted_vals[low] * (1.0 - frac) + sorted_vals[high] * frac)


# Win11's first build is 22000; anything below is Win10 for our booths.
WIN11_MIN_BUILD = 22000


def os_segment(machine: "dict") -> str:
    """Derive the ``win10`` / ``win11`` / ``unknown`` path segment.

    Prefers the OS build number (unambiguous: Win11 >= 22000); falls back to
    the caption string; returns ``"unknown"`` if neither is conclusive so a
    misfiled artefact is obvious rather than silently mislabeled. Shared by
    the timing-baseline and Mbient-soak artefact paths.

    Args:
        machine: The ``machine`` identity block.

    Returns:
        One of ``"win10"``, ``"win11"``, ``"unknown"``.
    """
    build_raw = machine.get("os_build")
    try:
        build = int(str(build_raw).strip())
    except (TypeError, ValueError):
        build = None
    if build is not None:
        return "win11" if build >= WIN11_MIN_BUILD else "win10"

    caption = (machine.get("os_caption") or "").lower()
    if "windows 11" in caption:
        return "win11"
    if "windows 10" in caption:
        return "win10"
    return "unknown"


_BT_RADIO_PS = (
    "Get-PnpDevice -Class Bluetooth -Status OK -ErrorAction SilentlyContinue | "
    "ForEach-Object { "
    "  $id = $_.InstanceId; "
    "  $drv = (Get-PnpDeviceProperty -InstanceId $id "
    "    -KeyName 'DEVPKEY_Device_DriverVersion' -ErrorAction SilentlyContinue).Data; "
    "  $date = (Get-PnpDeviceProperty -InstanceId $id "
    "    -KeyName 'DEVPKEY_Device_DriverDate' -ErrorAction SilentlyContinue).Data; "
    "  $mfg = (Get-PnpDeviceProperty -InstanceId $id "
    "    -KeyName 'DEVPKEY_Device_Manufacturer' -ErrorAction SilentlyContinue).Data; "
    "  [pscustomobject]@{ "
    "    Name = $_.FriendlyName; InstanceId = $id; "
    "    Manufacturer = $mfg; DriverVersion = $drv; DriverDate = $date "
    "  } "
    "} | ConvertTo-Json -Depth 3"
)

_BT_POWER_PS = (
    "Get-CimInstance -Namespace root/WMI -ClassName MSPower_DeviceEnable "
    "-ErrorAction SilentlyContinue | "
    "Where-Object { $_.InstanceName -match 'BTH|Bluetooth' } | "
    "Select-Object InstanceName, Enable | ConvertTo-Json -Depth 3"
)


def collect_bluetooth_radios(
    include_power: bool = False,
) -> "tuple[list, list[CollectionError]]":
    """Enumerate Bluetooth radios (name / driver / date) and, optionally, the
    radio power-management ("allow the computer to turn off this device")
    state — which #759 concern #4 flags as a Win11 default change.

    Single source of truth shared by ``win11_readiness.py`` (hardware floor)
    and ``mbient_soak.py`` (BLE soak run context). PowerShell failures are
    returned as :class:`CollectionError` rather than raised so the caller can
    still emit a useful artefact.

    Args:
        include_power: Also query ``MSPower_DeviceEnable`` and attach a
            best-effort ``power_mgmt`` list (each ``{instance_name, enable}``;
            ``enable=False`` means power-saving will NOT turn the radio off).

    Returns:
        ``(radios, errors)``. ``radios`` is a list of dicts; when
        ``include_power`` and the query succeeds, a final element
        ``{"power_mgmt": [...]}`` is appended so the shape stays a plain list.
    """
    radios: list = []
    errors: list = []
    try:
        info = ps_json(_BT_RADIO_PS)
        if isinstance(info, dict):
            info = [info]
        for entry in info or []:
            radios.append(
                {
                    "name": entry.get("Name"),
                    "instance_id": entry.get("InstanceId"),
                    "manufacturer": entry.get("Manufacturer"),
                    "driver_version": entry.get("DriverVersion"),
                    "driver_date": parse_ps_date(entry.get("DriverDate")),
                }
            )
    except Exception as exc:  # noqa: BLE001
        errors.append(CollectionError.from_exception("bluetooth.radios", exc))

    if include_power:
        try:
            pw = ps_json(_BT_POWER_PS)
            if isinstance(pw, dict):
                pw = [pw]
            radios.append(
                {
                    "power_mgmt": [
                        {
                            "instance_name": e.get("InstanceName"),
                            "enable": e.get("Enable"),
                        }
                        for e in (pw or [])
                    ]
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(CollectionError.from_exception("bluetooth.power_mgmt", exc))

    return radios, errors
