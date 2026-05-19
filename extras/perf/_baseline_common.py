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
import socket
import subprocess
from dataclasses import dataclass
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
