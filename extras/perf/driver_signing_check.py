"""Authenticode signing check over vendor SDK/driver files (#763).

Win11 enforces driver signing more strictly than Win10. If a Win11 update
breaks the signature on a previously-signed vendor ``.sys`` / ``.dll``
(FLIR/Spinnaker, RealSense, SR-Research/EyeLink, Apple Mobile Device), the
device silently stops loading. This runs ``Get-AuthenticodeSignature`` over
the given vendor paths and emits the shared envelope so a Win10 baseline can
be diffed against Win11.

Vendor install dirs vary per booth, so pass them with ``--path`` (repeatable;
documented per vendor in ``docs/win11_vendor_compat.md``). A small set of
common default locations is probed best-effort. Off-booth (no vendor dirs)
this emits an honest ``no_files`` artefact rather than a fake pass.

Usage::

    uv run python extras/perf/driver_signing_check.py \\
        [--path "C:\\Program Files\\Teledyne\\Spinnaker"] [--path ...] \\
        [--max-files 400] [--out PATH] [--no-json] [--stdout] [--strict]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from _baseline_common import (
    CollectionError,
    build_envelope,
    collect_os_identity,
    os_segment,
    resolved_log_dir,
    run_powershell,
)

SCHEMA_NAME = "driver_signing"
SCHEMA_VERSION = 1

# Best-effort default roots; only those that exist are scanned.
_DEFAULT_ROOTS = (
    r"C:\Program Files\Teledyne",
    r"C:\Program Files\FLIR Systems",
    r"C:\Program Files (x86)\Intel RealSense SDK 2.0",
    r"C:\Program Files (x86)\SR Research",
    r"C:\Program Files\Common Files\Apple\Mobile Device Support",
)


def _signing_ps(roots: List[str], max_files: int) -> str:
    """PowerShell: glob .sys/.dll under roots, Authenticode-check, JSON out."""
    quoted = ",".join(f"'{r}'" for r in roots)
    return (
        f"$roots=@({quoted}); "
        "$files=foreach($r in $roots){ if(Test-Path $r){ "
        "Get-ChildItem -Path $r -Recurse -Include *.sys,*.dll "
        "-ErrorAction SilentlyContinue } }; "
        f"$files | Select-Object -First {int(max_files)} | ForEach-Object {{ "
        "$s=Get-AuthenticodeSignature $_.FullName; "
        "[pscustomobject]@{ Path=$_.FullName; Status=[string]$s.Status; "
        "Signer=$(if($s.SignerCertificate){$s.SignerCertificate.Subject}"
        "else{$null}) } }} | ConvertTo-Json -Depth 3"
    )


def summarize(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate per-file signature rows. Pure; the unit-test seam.

    ``not_valid`` is the headline -- a Win11 signing break shows up as a
    file whose ``Status`` is no longer ``Valid``.
    """
    n = len(files)
    by_status: Dict[str, int] = {}
    not_valid: List[Dict[str, Any]] = []
    for f in files:
        st = str(f.get("Status") or "Unknown")
        by_status[st] = by_status.get(st, 0) + 1
        if st != "Valid":
            not_valid.append({"path": f.get("Path"), "status": st})
    return {
        "n_files": n,
        "by_status": by_status,
        "n_not_valid": len(not_valid),
        "not_valid": not_valid,
    }


def derive_verdict(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Honest capture verdict; never pass/fail for the OS question."""
    reasons = [
        "Signing capture. Regression is a comparison: diff against the "
        "locked Win10 baseline (sdk_compare.py)."
    ]
    if metrics["n_files"] == 0:
        reasons.append(
            "No vendor .sys/.dll found under the given paths -- pass "
            "--path with the booth's real vendor install dirs."
        )
        category = "NO_FILES"
    elif metrics["n_not_valid"] > 0:
        reasons.append(
            f"{metrics['n_not_valid']}/{metrics['n_files']} files are not "
            f"'Valid' ({metrics['by_status']}) -- a Win11 signing break "
            f"silently stops the driver loading."
        )
        category = "DEGRADED"
    else:
        category = "OK"
    return {"category": category, "reasons": reasons, "remediation_hints": []}


def collect(roots: List[str], max_files: int) -> tuple:
    """Run the PowerShell signing check. Returns ``(files, errors)``."""
    errors: List[CollectionError] = []
    try:
        raw = run_powershell(_signing_ps(roots, max_files), timeout=180)
        files = json.loads(raw) if raw else []
        if isinstance(files, dict):
            files = [files]
    except Exception as exc:  # noqa: BLE001
        errors.append(CollectionError.from_exception("driver_signing", exc))
        files = []
    return files, errors


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--path",
        action="append",
        default=[],
        help="Vendor install dir to scan (repeatable).",
    )
    p.add_argument(
        "--max-files", type=int, default=400, help="Cap files checked (default 400)."
    )
    p.add_argument("--out", type=Path, help="Output path override.")
    p.add_argument("--no-json", action="store_true", help="Do not write the JSON file.")
    p.add_argument(
        "--stdout", action="store_true", help="Also print the JSON envelope to stdout."
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any file is not 'Valid'.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    roots = args.path or list(_DEFAULT_ROOTS)

    print(
        f"Authenticode-checking vendor files under {len(roots)} root(s)...",
        file=sys.stderr,
    )
    files, errors = collect(roots, args.max_files)
    metrics = summarize(files)
    machine, os_errors = collect_os_identity(None)
    errors.extend(os_errors)
    payload = build_envelope(
        schema_name=SCHEMA_NAME,
        schema_version=SCHEMA_VERSION,
        machine=machine,
        blocks={"roots": roots, "signing": metrics},
        verdict=derive_verdict(metrics),
        errors=errors,
    )

    out_path = args.out or (
        resolved_log_dir(SCHEMA_NAME)
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
        f"Verdict: {payload['verdict']['category']} "
        f"({metrics['n_files']} files, {metrics['n_not_valid']} not valid)",
        file=sys.stderr,
    )
    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    if args.strict and payload["verdict"]["category"] == "DEGRADED":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
