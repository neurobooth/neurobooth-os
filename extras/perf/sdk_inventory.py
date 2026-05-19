"""Vendor-SDK / driver / firmware inventory for the Win10 -> Win11 decision.

Issue #763 (concern #5 of #759), suggested-approach step 1 -- build this
first; it is also the per-run header shape the other harnesses reuse. It
answers: *which* SDK / driver / firmware build is actually on this booth, so
"it works on Win11" becomes falsifiable (you can tell whether you are testing
the same build as Win10).

Runs every device probe in **inventory mode** (version + enumerate, no
frame grab) plus GPU / USB-host-controller / audio enumeration, and emits the
shared ``_baseline_common`` envelope. Probes **fail loudly** when a vendor
SDK is absent (recorded as ``sdk_absent``) -- they never fall back to a mock.
EyeLink is deferred to its own follow-up (see ``docs/win11_vendor_compat.md``).

Off-booth (no vendor SDKs / devices) this still emits a valid artefact with
every probe ``sdk_absent`` / ``no_device`` -- honest, not fabricated.

Usage::

    uv run python extras/perf/sdk_inventory.py [--out PATH] [--no-json]
        [--stdout] [--strict]

Default output: ``<log_dir>/sdk_inventory/<os>/<hostname>.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from _baseline_common import os_segment, resolved_log_dir
from _sdk_probe import PROBES, collect_host_inventory, to_envelope

SCHEMA_NAME = "sdk_inventory"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--out",
        type=Path,
        help="Output path. Default: " "<log_dir>/sdk_inventory/<os>/<hostname>.json.",
    )
    p.add_argument(
        "--no-json",
        action="store_true",
        help="Do not write the JSON file (stdout/console only).",
    )
    p.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the JSON envelope to stdout.",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if any probe is not 'ok' (CI gate). Off by "
        "default: this is an informational capture.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    print("Collecting SDK / driver / firmware inventory...", file=sys.stderr)
    probes = [fn(smoke=False) for fn in PROBES.values()]
    host, host_errors = collect_host_inventory()
    payload = to_envelope(SCHEMA_NAME, probes, host=host, extra_errors=host_errors)

    machine = payload["machine"]
    out_path = args.out or (
        resolved_log_dir("sdk_inventory")
        / os_segment(machine)
        / f"{machine.get('hostname', 'unknown')}.json"
    )
    if not args.no_json:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        print(f"Wrote: {out_path}", file=sys.stderr)

    verdict = payload["verdict"]
    print(f"Verdict: {verdict['category']}", file=sys.stderr)
    for p in probes:
        line = f"  {p.device:<8s} {p.sdk:<13s} {p.status}"
        if p.sdk_version:
            line += f"  sdk={p.sdk_version}"
        if p.firmware:
            line += f"  fw={p.firmware}"
        print(line, file=sys.stderr)
    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    if args.strict and verdict["category"] != "OK":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
