"""Snapshot a booth machine's Windows 11 minimum-hardware-floor compliance.

Captures TPM, Secure Boot, BIOS mode, CPU, RAM, disk, GPU, Bluetooth radio,
and vendor-software inventory into a single JSON artefact under
``extras/perf/baselines/win11_readiness/<hostname>.json``.

Scope is concern #9 of issue #759 (Windows 11 upgrade evaluation) and is
the deliverable of issue #767. The output is data, not a decision — a
triage step compares CPU names against Microsoft's published Win11 CPU
list (which moves over time and is therefore not hard-coded here) to
classify each booth as PASS / UPGRADEABLE / HARDWARE_FAIL.

Usage::

    python extras/perf/win11_readiness.py [--role CTR|STM|ACQ|spare] [--out PATH]

Run with the booth's normal user; no admin elevation is required for the
read-only queries used below.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


SCHEMA_VERSION = 1
SCHEMA_NAME = "win11_readiness"

# Substrings (case-insensitive) used to pick neurobooth-relevant entries out
# of the Uninstall registry hive. Kept broad; the triage step narrows.
VENDOR_SOFTWARE_KEYWORDS = (
    "eyelink",
    "sr research",
    "spinnaker",
    "flir",
    "teledyne",
    "realsense",
    "intel realsense",
    "apple mobile device",
    "apple application support",
    "psychopy",
)


@dataclass
class CollectionError:
    """A single non-fatal failure during data collection."""

    field: str
    message: str


@dataclass
class Snapshot:
    """Accumulator for the JSON payload."""

    machine: dict = field(default_factory=dict)
    win11_floor: dict = field(default_factory=dict)
    neurobooth_extras: dict = field(default_factory=dict)
    verdict: dict = field(default_factory=dict)
    errors: list[CollectionError] = field(default_factory=list)

    def record_error(self, where: str, exc: BaseException) -> None:
        self.errors.append(CollectionError(field=where, message=f"{type(exc).__name__}: {exc}"))


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


def collect_machine(snap: Snapshot, role: Optional[str]) -> None:
    """Populate :attr:`Snapshot.machine` with hostname, role, and OS identity."""
    snap.machine["hostname"] = socket.gethostname()
    if role:
        snap.machine["role"] = role
    try:
        info = ps_json(
            "Get-CimInstance Win32_OperatingSystem | "
            "Select-Object Caption, Version, BuildNumber, OSArchitecture | "
            "ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            snap.machine["os_caption"] = info.get("Caption")
            snap.machine["os_version"] = info.get("Version")
            snap.machine["os_build"] = info.get("BuildNumber")
            snap.machine["os_arch"] = info.get("OSArchitecture")
    except Exception as exc:  # noqa: BLE001
        snap.record_error("machine.os", exc)


def collect_tpm(snap: Snapshot) -> None:
    """Populate ``win11_floor.tpm``. The SpecVersion comes from Win32_Tpm because
    ``Get-Tpm`` does not expose it."""
    payload: dict[str, Any] = {}
    try:
        get_tpm = ps_json(
            "Get-Tpm | Select-Object TpmPresent, TpmReady, TpmEnabled, "
            "TpmActivated, TpmOwned | ConvertTo-Json -Depth 3"
        )
        if isinstance(get_tpm, dict):
            payload["present"] = get_tpm.get("TpmPresent")
            payload["ready"] = get_tpm.get("TpmReady")
            payload["enabled"] = get_tpm.get("TpmEnabled")
            payload["activated"] = get_tpm.get("TpmActivated")
            payload["owned"] = get_tpm.get("TpmOwned")
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.tpm.get_tpm", exc)

    try:
        win32_tpm = ps_json(
            r'Get-CimInstance -Namespace "root\CIMV2\Security\MicrosoftTpm" '
            r"-Class Win32_Tpm -ErrorAction Stop | "
            r"Select-Object SpecVersion, ManufacturerVersion, "
            r"ManufacturerIdTxt | ConvertTo-Json -Depth 3"
        )
        if isinstance(win32_tpm, dict):
            payload["spec_version"] = win32_tpm.get("SpecVersion")
            payload["manufacturer_version"] = win32_tpm.get("ManufacturerVersion")
            payload["manufacturer_id"] = (win32_tpm.get("ManufacturerIdTxt") or "").strip()
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.tpm.win32_tpm", exc)

    snap.win11_floor["tpm"] = payload


def collect_secure_boot(snap: Snapshot) -> None:
    """Populate ``win11_floor.secure_boot``.

    ``Confirm-SecureBootUEFI`` raises on legacy-BIOS machines instead of
    returning False, so we trap the exception and surface ``supported=False``.
    """
    payload: dict[str, Any] = {"supported": None, "enabled": None}
    try:
        result = run_powershell(
            "try { "
            "  $r = Confirm-SecureBootUEFI; "
            "  Write-Output ('SUPPORTED:' + $r) "
            "} catch { Write-Output ('UNSUPPORTED:' + $_.Exception.Message) }"
        )
        if result.startswith("SUPPORTED:"):
            payload["supported"] = True
            payload["enabled"] = result.split(":", 1)[1].strip().lower() == "true"
        else:
            payload["supported"] = False
            payload["enabled"] = False
            payload["note"] = result.split(":", 1)[1].strip() if ":" in result else result
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.secure_boot", exc)
    snap.win11_floor["secure_boot"] = payload


def collect_bios_mode(snap: Snapshot) -> None:
    """Populate ``win11_floor.bios_mode`` (``"UEFI"`` or ``"Legacy"``)."""
    try:
        raw = run_powershell("(Get-ComputerInfo -Property BiosFirmwareType).BiosFirmwareType")
        if raw.lower() == "uefi":
            snap.win11_floor["bios_mode"] = "UEFI"
        elif raw.lower() == "bios":
            snap.win11_floor["bios_mode"] = "Legacy"
        else:
            snap.win11_floor["bios_mode"] = raw or None
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.bios_mode", exc)
        snap.win11_floor["bios_mode"] = None


def collect_cpu(snap: Snapshot) -> None:
    """Populate ``win11_floor.cpu``.

    We deliberately do NOT classify the CPU as supported/unsupported here:
    Microsoft's Win11 supported-CPU list moves; baking it in would rot.
    """
    try:
        info = ps_json(
            "Get-CimInstance Win32_Processor | "
            "Select-Object Name, Manufacturer, NumberOfCores, "
            "NumberOfLogicalProcessors, MaxClockSpeed, Description, ProcessorId | "
            "ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            info = [info]
        cpus = []
        for entry in info or []:
            cpus.append(
                {
                    "name": (entry.get("Name") or "").strip(),
                    "manufacturer": entry.get("Manufacturer"),
                    "cores": entry.get("NumberOfCores"),
                    "threads": entry.get("NumberOfLogicalProcessors"),
                    "max_clock_mhz": entry.get("MaxClockSpeed"),
                    "description": entry.get("Description"),
                    "processor_id": entry.get("ProcessorId"),
                }
            )
        snap.win11_floor["cpu"] = cpus[0] if len(cpus) == 1 else cpus
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.cpu", exc)


def collect_memory_and_disk(snap: Snapshot) -> None:
    """Populate ``win11_floor.ram_bytes`` and ``win11_floor.disks``."""
    try:
        info = ps_json(
            "Get-CimInstance Win32_ComputerSystem | "
            "Select-Object TotalPhysicalMemory | ConvertTo-Json -Depth 2"
        )
        if isinstance(info, dict):
            mem = info.get("TotalPhysicalMemory")
            snap.win11_floor["ram_bytes"] = int(mem) if mem is not None else None
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.ram_bytes", exc)

    try:
        info = ps_json(
            "Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
            "Select-Object DeviceID, FreeSpace, Size | ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            info = [info]
        disks = []
        for entry in info or []:
            disks.append(
                {
                    "drive": entry.get("DeviceID"),
                    "free_bytes": int(entry.get("FreeSpace") or 0),
                    "size_bytes": int(entry.get("Size") or 0),
                }
            )
        snap.win11_floor["disks"] = disks
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.disks", exc)


def collect_gpu(snap: Snapshot) -> None:
    """Populate ``win11_floor.gpus``.

    WDDM version is not directly exposed via Win32_VideoController. Capturing
    it would require ``dxdiag /t``, a slow blocking call; we skip it here and
    leave WDDM verification to the triage step on any borderline booth.
    """
    try:
        info = ps_json(
            "Get-CimInstance Win32_VideoController | "
            "Select-Object Name, DriverVersion, DriverDate, AdapterRAM, "
            "VideoProcessor, VideoModeDescription | ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            info = [info]
        gpus = []
        for entry in info or []:
            gpus.append(
                {
                    "name": entry.get("Name"),
                    "driver_version": entry.get("DriverVersion"),
                    "driver_date": _parse_ps_date(entry.get("DriverDate")),
                    "video_ram_bytes": int(entry.get("AdapterRAM") or 0),
                    "video_processor": entry.get("VideoProcessor"),
                    "video_mode": entry.get("VideoModeDescription"),
                }
            )
        snap.win11_floor["gpus"] = gpus
    except Exception as exc:  # noqa: BLE001
        snap.record_error("win11_floor.gpus", exc)


def _parse_ps_date(value: Any) -> Any:
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


def collect_bluetooth(snap: Snapshot) -> None:
    """Populate ``neurobooth_extras.bluetooth`` with radio and driver versions."""
    try:
        info = ps_json(
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
        if isinstance(info, dict):
            info = [info]
        radios = []
        for entry in info or []:
            radios.append(
                {
                    "name": entry.get("Name"),
                    "instance_id": entry.get("InstanceId"),
                    "manufacturer": entry.get("Manufacturer"),
                    "driver_version": entry.get("DriverVersion"),
                    "driver_date": _parse_ps_date(entry.get("DriverDate")),
                }
            )
        snap.neurobooth_extras["bluetooth"] = radios
    except Exception as exc:  # noqa: BLE001
        snap.record_error("neurobooth_extras.bluetooth", exc)


def collect_vendor_software(snap: Snapshot) -> None:
    """Populate ``neurobooth_extras.vendor_software`` from the Uninstall registry.

    We read both 64-bit and 32-bit hives. ``Win32_Product`` would be the WMI
    way to get the same information, but enumerating it triggers MSI
    self-repair for every installed product — this approach is purely
    registry-read and safe.
    """
    try:
        info = ps_json(
            r"$paths = @("
            r"  'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*',"
            r"  'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*'"
            r"); "
            r"Get-ItemProperty -Path $paths -ErrorAction SilentlyContinue | "
            r"Where-Object { $_.DisplayName } | "
            r"Select-Object DisplayName, DisplayVersion, Publisher, InstallDate | "
            r"ConvertTo-Json -Depth 3"
        )
        if isinstance(info, dict):
            info = [info]
        matches = []
        for entry in info or []:
            name = (entry.get("DisplayName") or "").strip()
            haystack = name.lower()
            if any(kw in haystack for kw in VENDOR_SOFTWARE_KEYWORDS):
                matches.append(
                    {
                        "name": name,
                        "version": entry.get("DisplayVersion"),
                        "publisher": entry.get("Publisher"),
                        "install_date": entry.get("InstallDate"),
                    }
                )
        snap.neurobooth_extras["vendor_software"] = sorted(matches, key=lambda d: d["name"].lower())
    except Exception as exc:  # noqa: BLE001
        snap.record_error("neurobooth_extras.vendor_software", exc)


def derive_verdict(snap: Snapshot) -> None:
    """Apply the Win11 floor rules to the captured data and write a verdict.

    Verdict categories:
        PASS -- every checked floor item is satisfied; CPU may still need
            manual cross-check against the Microsoft list.
        UPGRADEABLE -- one or more items are off but firmware-toggleable
            (TPM disabled, Secure Boot off, BIOS in Legacy mode).
        HARDWARE_FAIL -- one or more items cannot be fixed without
            hardware replacement (TPM absent, TPM < 2.0, RAM < 4 GB,
            system disk < 64 GB free).
    """
    reasons: list[str] = []
    hints: list[str] = []
    fail_reasons: list[str] = []

    floor = snap.win11_floor

    tpm = floor.get("tpm") or {}
    if tpm.get("present") is False:
        fail_reasons.append("TPM not present")
    else:
        spec = tpm.get("spec_version")
        if spec and "2.0" not in str(spec):
            fail_reasons.append(f"TPM spec_version={spec} (need 2.0)")
        if tpm.get("present") and not tpm.get("enabled"):
            reasons.append("TPM present but disabled")
            hints.append("Enable TPM in firmware (often labeled 'PTT' on Intel or 'fTPM' on AMD)")

    sb = floor.get("secure_boot") or {}
    if sb.get("supported") is False:
        reasons.append("Secure Boot not supported (likely Legacy/CSM)")
        hints.append("Switch firmware to UEFI mode and enable Secure Boot")
    elif sb.get("supported") and not sb.get("enabled"):
        reasons.append("Secure Boot supported but disabled")
        hints.append("Enable Secure Boot in firmware")

    if floor.get("bios_mode") == "Legacy":
        reasons.append("Firmware booting in Legacy BIOS mode")
        hints.append("Convert system disk to GPT and switch firmware to UEFI")

    ram = floor.get("ram_bytes") or 0
    if 0 < ram < 4 * 1024**3:
        fail_reasons.append(f"RAM {ram / 1024**3:.1f} GiB (need >= 4 GiB)")

    disks = floor.get("disks") or []
    system_disk = next((d for d in disks if (d.get("drive") or "").upper().startswith("C")), None)
    if system_disk and system_disk.get("size_bytes", 0) and system_disk["size_bytes"] < 64 * 1024**3:
        fail_reasons.append(
            f"System disk {system_disk['size_bytes'] / 1024**3:.1f} GiB (need >= 64 GiB)"
        )

    if fail_reasons:
        category = "HARDWARE_FAIL"
        all_reasons = fail_reasons + reasons
    elif reasons:
        category = "UPGRADEABLE"
        all_reasons = reasons
    else:
        category = "PASS"
        all_reasons = []

    all_reasons.append("CPU not auto-classified -- compare CPU name to Microsoft's Win11 supported list")

    snap.verdict = {
        "category": category,
        "reasons": all_reasons,
        "remediation_hints": hints,
    }


def to_payload(snap: Snapshot) -> dict[str, Any]:
    """Assemble the final JSON-serializable payload."""
    return {
        "schema_version": SCHEMA_VERSION,
        "schema_name": SCHEMA_NAME,
        "captured_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
        "machine": snap.machine,
        "win11_floor": snap.win11_floor,
        "neurobooth_extras": snap.neurobooth_extras,
        "verdict": snap.verdict,
        "collection_errors": [
            {"field": e.field, "message": e.message} for e in snap.errors
        ],
    }


def default_output_path(hostname: str) -> Path:
    """Return the conventional output path under ``extras/perf/baselines/win11_readiness/``."""
    here = Path(__file__).resolve().parent
    return here / "baselines" / "win11_readiness" / f"{hostname}.json"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--role",
        choices=["CTR", "STM", "ACQ", "spare"],
        help="Booth role for this machine; recorded in the JSON for triage.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output file path. Defaults to "
        "extras/perf/baselines/win11_readiness/<hostname>.json.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout in addition to writing the file.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    snap = Snapshot()

    print("Collecting Windows 11 readiness snapshot...", file=sys.stderr)

    collect_machine(snap, args.role)
    collect_tpm(snap)
    collect_secure_boot(snap)
    collect_bios_mode(snap)
    collect_cpu(snap)
    collect_memory_and_disk(snap)
    collect_gpu(snap)
    collect_bluetooth(snap)
    collect_vendor_software(snap)
    derive_verdict(snap)

    payload = to_payload(snap)
    out_path = args.out or default_output_path(snap.machine.get("hostname", "unknown"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    verdict = payload["verdict"]["category"]
    print(f"Verdict: {verdict}", file=sys.stderr)
    print(f"Wrote: {out_path}", file=sys.stderr)
    if snap.errors:
        print(f"Collection errors: {len(snap.errors)} (see JSON 'collection_errors')", file=sys.stderr)

    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
