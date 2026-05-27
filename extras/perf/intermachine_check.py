"""CTR-side harness: exercise the inter-machine plumbing each booth depends on.

Issue #764 / concern #2 of #759. Validates that the four remote primitives
in ``neurobooth_os/netcomm/client.py`` plus the ``admin$`` SMB share work
end-to-end against every configured booth, before a Windows 11 upgrade has
a chance to silently regress one of them. The runbook the harness checks
against is ``docs/inter_machine_setup.md`` (Section 8 "Expected state").

Primitives exercised per booth:

* ``tasklist /S /U /P`` -- RPC over named pipes, NTLM auth
* ``Get-CimInstance -CimSession (Dcom)`` -- DCOM (the post-PR-#770 path)
* ``SCHTASKS /S /U /P /Query`` -- RPC + DCOM (Task Scheduler Remote)
* ``SCHTASKS /S /U /P /Create /XML`` + ``/Delete`` round-trip -- same
  transport plus the ``admin$`` SMB read SCHTASKS depends on when
  transferring the task XML. The task is created Enabled=false and is
  deleted immediately; no scheduled work ever runs.
* ``taskkill /S /U /P /PID 0 /F`` -- expected to fail with
  ``ERROR_NOT_FOUND``; a structured "no such process" reply confirms the
  RPC/DCOM round-trip without killing anything.
* ``net use \\<host>\admin$ /USER:<u> <p>`` -- direct SMB connect test
  (separate signal from the SCHTASKS-implied SMB dependency above).

Emits the shared ``_baseline_common`` envelope under
``<log_dir>/intermachine_check/<os>/<hostname>.json`` so the artefact
diffs cleanly against the four sibling baselines coordinated in #768.

Reads booth credentials from ``cfg.neurobooth_config.server_by_name``;
no flags pass them on the command line. Targets default to every
configured remote service (presentation + acquisition_*); the current
machine's own ``control`` entry is skipped because there is no
cross-machine plumbing to exercise against localhost.

Usage::

    uv run python extras/perf/intermachine_check.py [--out PATH]
        [--targets presentation,acquisition_0] [--stdout] [--strict]
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
import xml.sax.saxutils as _saxutils
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple

from _baseline_common import (
    CollectionError,
    build_envelope,
    collect_os_identity,
    os_segment,
    resolved_log_dir,
)

SCHEMA_VERSION = 1
SCHEMA_NAME = "intermachine_check"

# Treat a probe that finishes in under this many milliseconds as "fast" in
# the summary line; longer than this on a same-LAN booth often points at
# auth retry / fallback under the hood (NTLMv2 hardening, profile flip).
SLOW_PROBE_MS = 3000.0

# taskkill on a non-existent PID returns 128 with stderr like
# "ERROR: The process \"0\" not found." Treat that exit code as the
# "expected fail" signal -- it proves the transport completed without
# touching any real process.
TASKKILL_NOTFOUND_RC = 128


@dataclass
class ProbeResult:
    primitive: str
    transport: str
    status: str  # "ok" | "expected_fail" | "fail" | "skip"
    duration_ms: float
    exit_code: Optional[int] = None
    stderr_excerpt: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None or k in ("status",)}


@dataclass
class TargetResult:
    name: str
    host: str
    user: str
    probes: List[ProbeResult] = field(default_factory=list)
    verdict: str = "PASS"  # PASS | DEGRADED | FAIL
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        out: dict = {
            "name": self.name,
            "host": self.host,
            "user": self.user,
            "verdict": self.verdict,
        }
        if self.skip_reason:
            out["skip_reason"] = self.skip_reason
        out["probes"] = [p.to_dict() for p in self.probes]
        return out


def _clip(text: Optional[str], limit: int = 500) -> Optional[str]:
    if not text:
        return None
    text = text.strip()
    return text[:limit] if len(text) > limit else (text or None)


def _run(cmd: List[str], timeout: float, env: Optional[dict] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def _measure(fn) -> Tuple[Any, float]:
    t0 = time.monotonic()
    result = fn()
    return result, (time.monotonic() - t0) * 1000.0


def probe_tasklist(host: str, user: str, password: str, timeout: float = 20.0) -> ProbeResult:
    """Exercise the named-pipe RPC + NTLM path used by ``get_python_pids``."""
    def _go():
        return _run(
            ["tasklist.exe", "/S", host, "/U", user, "/P", password, "/FO", "CSV", "/NH"],
            timeout=timeout,
        )
    try:
        result, ms = _measure(_go)
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            primitive="tasklist",
            transport="RPC over named pipes (NTLM)",
            status="fail",
            duration_ms=timeout * 1000.0,
            stderr_excerpt=_clip(str(exc)),
            note="timeout",
        )

    ok = result.returncode == 0
    return ProbeResult(
        primitive="tasklist",
        transport="RPC over named pipes (NTLM)",
        status="ok" if ok else "fail",
        duration_ms=ms,
        exit_code=result.returncode,
        stderr_excerpt=_clip(result.stderr),
    )


_PS_DCOM_PYTHON_PROCS = r"""
$ErrorActionPreference = 'Stop'
$securepw = ConvertTo-SecureString $env:NB_REMOTE_PASSWORD -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential($env:NB_REMOTE_USER, $securepw)
$opt = New-CimSessionOption -Protocol Dcom
$sess = New-CimSession -ComputerName $env:NB_REMOTE_HOST -Credential $cred -SessionOption $opt
try {
    Get-CimInstance -CimSession $sess -ClassName Win32_Process -Filter "Name='python.exe'" |
        Measure-Object | Select-Object -ExpandProperty Count
} finally {
    Remove-CimSession $sess
}
"""


def probe_dcom_ciminstance(host: str, user: str, password: str, timeout: float = 30.0) -> ProbeResult:
    """Exercise the DCOM CimSession path that replaced WMIC in PR #770.

    Credentials are passed via env vars to keep the password off the
    command line (same convention as ``client.py``'s production code).
    """
    qualified_user = user if "\\" in user else f"{host}\\{user}"
    env = {
        **os.environ,
        "NB_REMOTE_HOST": host,
        "NB_REMOTE_USER": qualified_user,
        "NB_REMOTE_PASSWORD": password or "",
    }

    def _go():
        return _run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _PS_DCOM_PYTHON_PROCS],
            timeout=timeout,
            env=env,
        )
    try:
        result, ms = _measure(_go)
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            primitive="get_ciminstance_dcom",
            transport="DCOM",
            status="fail",
            duration_ms=timeout * 1000.0,
            stderr_excerpt=_clip(str(exc)),
            note="timeout",
        )

    ok = result.returncode == 0
    return ProbeResult(
        primitive="get_ciminstance_dcom",
        transport="DCOM",
        status="ok" if ok else "fail",
        duration_ms=ms,
        exit_code=result.returncode,
        stderr_excerpt=_clip(result.stderr),
    )


def probe_schtasks_query(host: str, user: str, password: str, timeout: float = 20.0) -> ProbeResult:
    """Read-only Task Scheduler Remote round-trip."""
    def _go():
        return _run(
            ["SCHTASKS", "/Query", "/S", host, "/U", user, "/P", password, "/FO", "CSV", "/NH"],
            timeout=timeout,
        )
    try:
        result, ms = _measure(_go)
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            primitive="schtasks_query",
            transport="RPC + DCOM (Task Scheduler Remote)",
            status="fail",
            duration_ms=timeout * 1000.0,
            stderr_excerpt=_clip(str(exc)),
            note="timeout",
        )

    ok = result.returncode == 0
    return ProbeResult(
        primitive="schtasks_query",
        transport="RPC + DCOM (Task Scheduler Remote)",
        status="ok" if ok else "fail",
        duration_ms=ms,
        exit_code=result.returncode,
        stderr_excerpt=_clip(result.stderr),
    )


def _noop_task_xml(machine: str, user: str) -> str:
    """Minimal Task Scheduler XML that cannot run.

    Strict-mode Win11 schema validation accepts the EventTrigger pattern
    we use in production (``_build_task_xml`` in ``netcomm/client.py``);
    we mirror it here for the same reason, with the trigger pointing at
    an event ID nothing emits and the task itself Enabled=false /
    AllowStartOnDemand=false. The Action is ``cmd.exe /c exit 0`` purely
    so the schema validator accepts an Exec block; it never runs.
    """
    qualified_user = user if "\\" in user else f"{machine}\\{user}"
    user_xml = _saxutils.escape(qualified_user)
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        '  <Triggers>\n'
        '    <EventTrigger>\n'
        '      <Enabled>false</Enabled>\n'
        "      <Subscription>&lt;QueryList&gt;&lt;Query&gt;&lt;Select Path='Application'&gt;"
        "*[System/EventID=778]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>\n"
        '    </EventTrigger>\n'
        '  </Triggers>\n'
        '  <Principals>\n'
        '    <Principal id="Author">\n'
        f'      <UserId>{user_xml}</UserId>\n'
        '      <LogonType>InteractiveToken</LogonType>\n'
        '      <RunLevel>LeastPrivilege</RunLevel>\n'
        '    </Principal>\n'
        '  </Principals>\n'
        '  <Settings>\n'
        '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
        '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
        '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
        '    <AllowStartOnDemand>false</AllowStartOnDemand>\n'
        '    <Enabled>false</Enabled>\n'
        '    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>\n'
        '  </Settings>\n'
        '  <Actions Context="Author">\n'
        '    <Exec>\n'
        '      <Command>cmd.exe</Command>\n'
        '      <Arguments>/c exit 0</Arguments>\n'
        '    </Exec>\n'
        '  </Actions>\n'
        '</Task>\n'
    )


def probe_schtasks_xml_roundtrip(host: str, user: str, password: str,
                                 timeout: float = 30.0) -> ProbeResult:
    """Create + Delete a disabled no-op task. Exercises SMB ``admin$`` too.

    SCHTASKS ``/Create /XML`` pulls the XML file via SMB to ``\\<host>\\admin$``
    before registering it, so this probe is the only one that surfaces an
    SMB regression along the SCHTASKS path. The task is created
    Enabled=false / AllowStartOnDemand=false; it cannot run even if a
    cleanup failure leaves it registered.

    Always deletes in a finally; the task name is uniquified so concurrent
    runs against the same booth do not collide.
    """
    task_name = f"_nb_intermachine_probe_{uuid.uuid4().hex[:12]}"
    xml_content = _noop_task_xml(machine=host, user=user)

    fd, xml_path = tempfile.mkstemp(suffix=".xml")
    create_rc: Optional[int] = None
    create_stderr: Optional[str] = None
    delete_rc: Optional[int] = None
    delete_stderr: Optional[str] = None

    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(b"\xff\xfe")  # SCHTASKS /XML expects UTF-16 LE with BOM
            fh.write(xml_content.encode("utf-16-le"))

        def _create():
            return _run(
                ["SCHTASKS", "/Create", "/S", host, "/U", user, "/P", password,
                 "/TN", task_name, "/XML", xml_path, "/F"],
                timeout=timeout,
            )
        try:
            create_result, ms = _measure(_create)
            create_rc = create_result.returncode
            create_stderr = _clip(create_result.stderr)
        except subprocess.TimeoutExpired as exc:
            return ProbeResult(
                primitive="schtasks_xml_roundtrip",
                transport="RPC + DCOM + SMB (admin$ XML transfer)",
                status="fail",
                duration_ms=timeout * 1000.0,
                stderr_excerpt=_clip(str(exc)),
                note="create timeout",
            )

        if create_rc != 0:
            return ProbeResult(
                primitive="schtasks_xml_roundtrip",
                transport="RPC + DCOM + SMB (admin$ XML transfer)",
                status="fail",
                duration_ms=ms,
                exit_code=create_rc,
                stderr_excerpt=create_stderr,
                note="create failed",
            )

        def _delete():
            return _run(
                ["SCHTASKS", "/Delete", "/S", host, "/U", user, "/P", password,
                 "/TN", task_name, "/F"],
                timeout=timeout,
            )
        try:
            delete_result, delete_ms = _measure(_delete)
            delete_rc = delete_result.returncode
            delete_stderr = _clip(delete_result.stderr)
        except subprocess.TimeoutExpired as exc:
            return ProbeResult(
                primitive="schtasks_xml_roundtrip",
                transport="RPC + DCOM + SMB (admin$ XML transfer)",
                status="fail",
                duration_ms=ms + timeout * 1000.0,
                stderr_excerpt=_clip(str(exc)),
                note="delete timeout (task left registered, but Enabled=false)",
            )

        if delete_rc != 0:
            return ProbeResult(
                primitive="schtasks_xml_roundtrip",
                transport="RPC + DCOM + SMB (admin$ XML transfer)",
                status="fail",
                duration_ms=ms + delete_ms,
                exit_code=delete_rc,
                stderr_excerpt=delete_stderr,
                note=f"delete failed; task '{task_name}' may remain (Enabled=false)",
            )

        return ProbeResult(
            primitive="schtasks_xml_roundtrip",
            transport="RPC + DCOM + SMB (admin$ XML transfer)",
            status="ok",
            duration_ms=ms + delete_ms,
            exit_code=0,
        )
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass


def probe_taskkill_notfound(host: str, user: str, password: str,
                            timeout: float = 15.0) -> ProbeResult:
    """``taskkill /PID 0`` -- expected to fail with NOT_FOUND.

    A structured "no such process" reply proves the RPC/DCOM transport
    completed without touching any real process. Any other failure mode
    (network, auth, firewall) shows up as a different exit code.
    """
    def _go():
        return _run(
            ["taskkill", "/S", host, "/U", user, "/P", password, "/PID", "0", "/F"],
            timeout=timeout,
        )
    try:
        result, ms = _measure(_go)
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            primitive="taskkill_notfound",
            transport="RPC/DCOM",
            status="fail",
            duration_ms=timeout * 1000.0,
            stderr_excerpt=_clip(str(exc)),
            note="timeout",
        )

    if result.returncode == TASKKILL_NOTFOUND_RC:
        return ProbeResult(
            primitive="taskkill_notfound",
            transport="RPC/DCOM",
            status="expected_fail",
            duration_ms=ms,
            exit_code=result.returncode,
            note='exit 128 "process not found" = transport ok',
        )
    if result.returncode == 0:
        return ProbeResult(
            primitive="taskkill_notfound",
            transport="RPC/DCOM",
            status="fail",
            duration_ms=ms,
            exit_code=0,
            note="taskkill PID 0 unexpectedly returned 0; check remote state",
        )
    return ProbeResult(
        primitive="taskkill_notfound",
        transport="RPC/DCOM",
        status="fail",
        duration_ms=ms,
        exit_code=result.returncode,
        stderr_excerpt=_clip(result.stderr),
    )


def probe_admin_share_smb(host: str, user: str, password: str,
                          timeout: float = 20.0) -> ProbeResult:
    """``net use \\<host>\admin$`` round-trip.

    Surfaces a regression in SMB signing / SMB1-off / NTLM-against-SMB
    that would not show up in the SCHTASKS round-trip's exit code (the
    SCHTASKS layer can sometimes mask the underlying SMB error).
    """
    share = f"\\\\{host}\\admin$"
    def _connect():
        return _run(
            ["net", "use", share, password, f"/USER:{user}"],
            timeout=timeout,
        )
    def _disconnect():
        return _run(
            ["net", "use", share, "/DELETE", "/Y"],
            timeout=timeout,
        )

    try:
        result, ms = _measure(_connect)
    except subprocess.TimeoutExpired as exc:
        return ProbeResult(
            primitive="admin_share_smb",
            transport="SMB",
            status="fail",
            duration_ms=timeout * 1000.0,
            stderr_excerpt=_clip(str(exc)),
            note="connect timeout",
        )

    if result.returncode != 0:
        return ProbeResult(
            primitive="admin_share_smb",
            transport="SMB",
            status="fail",
            duration_ms=ms,
            exit_code=result.returncode,
            stderr_excerpt=_clip(result.stderr or result.stdout),
        )

    try:
        _disconnect()  # best-effort cleanup; never fails the probe
    except Exception:  # noqa: BLE001
        pass

    return ProbeResult(
        primitive="admin_share_smb",
        transport="SMB",
        status="ok",
        duration_ms=ms,
        exit_code=0,
    )


PROBES = (
    probe_tasklist,
    probe_dcom_ciminstance,
    probe_schtasks_query,
    probe_schtasks_xml_roundtrip,
    probe_taskkill_notfound,
    probe_admin_share_smb,
)


def run_target(name: str, host: str, user: str, password: str) -> TargetResult:
    """Run every probe against one booth and roll up a per-target verdict."""
    target = TargetResult(name=name, host=host, user=user)
    for probe_fn in PROBES:
        try:
            target.probes.append(probe_fn(host, user, password))
        except Exception as exc:  # noqa: BLE001
            target.probes.append(
                ProbeResult(
                    primitive=probe_fn.__name__,
                    transport="unknown",
                    status="fail",
                    duration_ms=0.0,
                    note=f"harness crash: {type(exc).__name__}: {exc}",
                )
            )

    # Verdict: PASS if every probe is ok/expected_fail. DEGRADED if the read
    # primitives pass but a write primitive (SCHTASKS XML roundtrip) fails.
    # FAIL if a read primitive fails.
    statuses = {p.primitive: p.status for p in target.probes}
    read_primitives = ("tasklist", "get_ciminstance_dcom", "schtasks_query")
    write_primitives = ("schtasks_xml_roundtrip", "admin_share_smb")

    read_ok = all(statuses.get(p) in ("ok", "expected_fail") for p in read_primitives)
    write_ok = all(statuses.get(p) in ("ok", "expected_fail") for p in write_primitives)

    if not read_ok:
        target.verdict = "FAIL"
    elif not write_ok:
        target.verdict = "DEGRADED"
    else:
        target.verdict = "PASS"
    return target


def _resolve_targets(requested: Optional[List[str]]) -> Tuple[List[Tuple[str, str, str, str]], List[CollectionError]]:
    """Return ``[(service_name, host, user, password), ...]`` for the targets to probe.

    Skips the current machine's ``control`` entry by default -- the cross-
    machine plumbing has nothing to validate against localhost. If a
    requested target has no password configured, it is dropped and an
    error is appended (mirroring ``client.py``'s `ConfigException` path,
    but the harness keeps running for the remaining booths).
    """
    errors: List[CollectionError] = []
    try:
        import neurobooth_os.config as _cfg
    except ImportError as exc:  # neurobooth_os not installed
        errors.append(CollectionError("config", f"neurobooth_os not importable: {exc}"))
        return [], errors

    if _cfg.neurobooth_config is None:
        try:
            _cfg.load_config(validate_paths=False)
        except Exception as exc:  # noqa: BLE001
            errors.append(CollectionError("config.load", f"{type(exc).__name__}: {exc}"))
            return [], errors

    nbc = _cfg.neurobooth_config
    if requested is None:
        names = ["presentation"] + [f"acquisition_{i}" for i in range(len(nbc.acquisition))]
    else:
        names = requested

    out: List[Tuple[str, str, str, str]] = []
    local_host = socket.gethostname().upper()
    for name in names:
        try:
            svc = nbc.server_by_name(name)
        except Exception as exc:  # noqa: BLE001
            errors.append(CollectionError(f"config.target.{name}", f"{type(exc).__name__}: {exc}"))
            continue
        if not svc.user or svc.password is None:
            errors.append(
                CollectionError(
                    f"config.target.{name}",
                    "no user/password configured (single-machine dev?) -- skipping",
                )
            )
            continue
        if svc.name.upper() == local_host:
            errors.append(
                CollectionError(
                    f"config.target.{name}",
                    f"resolves to the current machine ({local_host}); no cross-machine plumbing to probe",
                )
            )
            continue
        out.append((name, svc.name, svc.user, svc.password.get_secret_value()))
    return out, errors


def derive_overall_verdict(targets: List[TargetResult]) -> dict:
    if not targets:
        return {
            "category": "FAIL",
            "reasons": ["no targets resolved"],
            "remediation_hints": [
                "Ensure NB_CONFIG points at the booth's config and secrets.yaml has passwords"
            ],
        }
    per_verdict = {t.verdict for t in targets}
    if per_verdict == {"PASS"}:
        return {"category": "PASS", "reasons": [], "remediation_hints": []}
    failed = [t.name for t in targets if t.verdict == "FAIL"]
    degraded = [t.name for t in targets if t.verdict == "DEGRADED"]
    reasons: List[str] = []
    hints: List[str] = []
    if failed:
        reasons.append(f"read-primitive failure on: {', '.join(failed)}")
        hints.append(
            "Walk docs/inter_machine_setup.md sections 2-6 on the failing booth; "
            "the failing probe's 'transport' field identifies which section"
        )
        category = "FAIL"
    elif degraded:
        reasons.append(f"write-primitive failure on: {', '.join(degraded)}")
        hints.append(
            "Check SMB server config on the failing booth (Section 7 of the runbook); "
            "EnableSMB2Protocol=True and a non-Public NIC profile are the usual culprits"
        )
        category = "DEGRADED"
    else:
        category = "PASS"
    return {"category": category, "reasons": reasons, "remediation_hints": hints}


def to_payload(machine: dict, targets: List[TargetResult],
               errors: List[CollectionError]) -> dict:
    return build_envelope(
        schema_name=SCHEMA_NAME,
        schema_version=SCHEMA_VERSION,
        machine=machine,
        blocks={"targets": [t.to_dict() for t in targets]},
        verdict=derive_overall_verdict(targets),
        errors=errors,
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--out",
        type=Path,
        help="Output JSON path. Defaults to "
        "<log_dir>/intermachine_check/<os>/<hostname>.json.",
    )
    p.add_argument(
        "--targets",
        help="Comma-separated service names (e.g. 'presentation,acquisition_0'). "
        "Defaults to every configured remote service.",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Print the JSON envelope to stdout in addition to writing the file.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if the overall verdict is not PASS (CI gate).",
    )
    return p.parse_args(argv)


def _format_summary(target: TargetResult) -> str:
    line = f"  [{target.verdict}] {target.name} ({target.host})"
    for probe in target.probes:
        marker = {"ok": "ok", "expected_fail": "ok*", "fail": "FAIL", "skip": "skip"}.get(
            probe.status, probe.status
        )
        slow = " (slow)" if probe.duration_ms > SLOW_PROBE_MS else ""
        line += f"\n      {probe.primitive:<24s} {marker:<5s} {probe.duration_ms:6.0f}ms{slow}"
        if probe.status == "fail" and probe.stderr_excerpt:
            line += f" -- {probe.stderr_excerpt.splitlines()[0][:80]}"
    return line


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    print("Resolving targets from neurobooth config...", file=sys.stderr)
    requested = [s.strip() for s in args.targets.split(",")] if args.targets else None
    targets_spec, cfg_errors = _resolve_targets(requested)

    if cfg_errors:
        for err in cfg_errors:
            print(f"  config: {err.field}: {err.message}", file=sys.stderr)

    machine, machine_errors = collect_os_identity()
    machine["role"] = "control"

    target_results: List[TargetResult] = []
    for name, host, user, password in targets_spec:
        print(f"Probing {name} ({host}) ...", file=sys.stderr)
        target_results.append(run_target(name, host, user, password))

    errors = cfg_errors + machine_errors
    payload = to_payload(machine, target_results, errors)

    out_path = args.out or (
        resolved_log_dir("intermachine_check")
        / os_segment(machine)
        / f"{machine.get('hostname', 'unknown')}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    verdict = payload["verdict"]["category"]
    print(f"\nOverall verdict: {verdict}", file=sys.stderr)
    for tr in target_results:
        print(_format_summary(tr), file=sys.stderr)
    print(f"\nWrote: {out_path}", file=sys.stderr)

    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    if args.strict and verdict != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
