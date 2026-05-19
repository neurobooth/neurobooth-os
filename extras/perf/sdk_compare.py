"""Diff two SDK inventory/smoke artefacts (Win10 locked vs Win11) (#763).

Sibling of ``compare_timing.py`` / ``mbient_soak_compare.py``. #763
suggested-approach step 5: "diff against the Win10 baselines; fail loudly on
any SDK / driver / firmware version that has silently rolled." Here that
"failure" is a **flag for human review**, not an auto-fail (same convention
as the other comparators): a version roll is exactly what you want surfaced,
but whether it matters is a human call.

Compares the ``probes`` block emitted by ``sdk_inventory.py`` and the
``*_smoke.py`` scripts, keyed by ``device/sdk``. The headline signals:

* a probe ``status`` regressed (e.g. ``ok`` -> ``sdk_absent`` on Win11),
* ``sdk_version`` / ``driver_version`` / ``firmware`` / ``serial`` changed
  (the "silently rolled" case -- you are no longer testing the same build),
* a smoke action that passed on Win10 now fails.

Every raw before/after value is printed whether or not it is flagged. Pure
stdlib; no DB, no neurobooth stack; fully unit-tested.

Usage::

    uv run python extras/perf/sdk_compare.py \\
        extras/perf/baselines/sdk/win10/acq.json \\
        extras/perf/baselines/sdk/win11/acq.json \\
        [--json PATH] [--no-json] [--strict]
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from _baseline_common import build_envelope, resolved_log_dir

SCHEMA_VERSION = 1
SCHEMA_NAME = "sdk_comparison"

# Fields whose change between OSes means "you are not testing the same build".
_VERSION_FIELDS = ("sdk_version", "driver_version", "firmware", "serial")


def load_run(path: Path) -> Dict[str, Any]:
    """Read and JSON-parse one artefact (errors surfaced, not swallowed)."""
    return json.loads(path.read_text(encoding="utf-8"))


def _probes_by_key(payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for p in payload.get("probes", []) or []:
        out[f"{p.get('device')}/{p.get('sdk')}"] = p
    return out


def _os_label(machine: Dict[str, Any]) -> str:
    cap = machine.get("os_caption")
    build = machine.get("os_build")
    if cap and build:
        return f"{cap} (build {build})"
    return str(cap or build or "unknown")


def build_comparison(baseline: Dict[str, Any], pilot: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble the structured probe-by-probe comparison. Pure; test seam."""
    b_probes = _probes_by_key(baseline)
    p_probes = _probes_by_key(pilot)
    flags: List[str] = []
    table: Dict[str, Any] = {}

    for key in sorted(set(b_probes) | set(p_probes)):
        b = b_probes.get(key)
        p = p_probes.get(key)
        if b is None or p is None:
            table[key] = {
                "status": "not_comparable",
                "reason": f"probe present only in "
                f"{'pilot' if b is None else 'baseline'}",
            }
            flags.append(f"{key}: present in only one artefact.")
            continue

        cell: Dict[str, Any] = {
            "status": {"baseline": b.get("status"), "pilot": p.get("status")},
        }
        if b.get("status") == "ok" and p.get("status") != "ok":
            cell["status"]["flagged"] = True
            flags.append(
                f"{key}: status regressed {b.get('status')} -> "
                f"{p.get('status')} ({p.get('error') or 'see artefact'})."
            )

        for fld in _VERSION_FIELDS:
            bv, pv = b.get(fld), p.get(fld)
            entry = {"baseline": bv, "pilot": pv, "changed": bv != pv}
            if bv != pv and not (bv is None and pv is None):
                entry["flagged"] = True
                flags.append(
                    f"{key}: {fld} rolled {bv!r} -> {pv!r} "
                    f"(not the same build across OSes)."
                )
            cell[fld] = entry

        b_sm, p_sm = b.get("smoke_ok"), p.get("smoke_ok")
        cell["smoke_ok"] = {"baseline": b_sm, "pilot": p_sm}
        if b_sm is True and p_sm is False:
            cell["smoke_ok"]["flagged"] = True
            flags.append(f"{key}: smoke action passed on baseline, failed on pilot.")

        table[key] = cell

    schema_ok = baseline.get("schema_name") == pilot.get(
        "schema_name"
    ) and baseline.get("schema_version") == pilot.get("schema_version")
    if not schema_ok:
        flags.append(
            "schema mismatch: "
            f"{baseline.get('schema_name')}/v{baseline.get('schema_version')} "
            f"vs {pilot.get('schema_name')}/v{pilot.get('schema_version')}."
        )

    return {
        "os_transition": {
            "from": _os_label(baseline.get("machine", {})),
            "to": _os_label(pilot.get("machine", {})),
        },
        "schema": {
            "baseline": f"{baseline.get('schema_name')}"
            f"/v{baseline.get('schema_version')}",
            "pilot": f"{pilot.get('schema_name')}" f"/v{pilot.get('schema_version')}",
            "compatible": bool(schema_ok),
        },
        "probes": table,
        "pilot_machine": pilot.get("machine", {}),
        "flags": flags,
    }


def to_verdict(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """``REVIEW`` if anything was flagged; never ``FAIL``."""
    flags = comparison.get("flags", [])
    reasons = [
        "A flag means a human reviews with the numbers in hand -- not a "
        "failure. A rolled SDK/driver/firmware version is expected to be "
        "flagged: it means Win11 is not running the same build as the Win10 "
        "baseline."
    ]
    reasons += flags
    return {
        "category": "REVIEW" if flags else "MATCH",
        "reasons": reasons,
        "remediation_hints": (
            [
                "Confirm whether each rolled version is intended; re-pin/re-"
                "install to match the Win10 baseline if a comparison must be "
                "apples-to-apples."
            ]
            if flags
            else []
        ),
    }


def render(comparison: Dict[str, Any]) -> str:
    out: List[str] = []
    ot = comparison["os_transition"]
    out.append("=" * 78)
    out.append("SDK / DRIVER / FIRMWARE COMPARISON  --  Win10 -> Win11")
    out.append(f"  {ot['from']}  ->  {ot['to']}")
    if not comparison["schema"]["compatible"]:
        out.append(
            f"  SCHEMA: {comparison['schema']['baseline']} vs "
            f"{comparison['schema']['pilot']}"
        )
    out.append("=" * 78)
    for key, cell in comparison["probes"].items():
        if cell.get("status") == "not_comparable":
            out.append(f"\n{key}: NOT COMPARABLE ({cell['reason']})")
            continue
        st = cell["status"]
        sflag = "  <== FLAG" if st.get("flagged") else ""
        out.append(f"\n{key}: status {st['baseline']} -> {st['pilot']}{sflag}")
        for fld in _VERSION_FIELDS + ("smoke_ok",):
            c = cell.get(fld, {})
            fflag = "  <== FLAG" if c.get("flagged") else ""
            out.append(
                f"  {fld:<15s} {str(c.get('baseline')):<22s} -> "
                f"{str(c.get('pilot'))}{fflag}"
            )
    verdict = to_verdict(comparison)
    out.append(f"\nVERDICT: {verdict['category']}")
    for r in verdict["reasons"]:
        out.append(f"  - {r}")
    out.append("")
    return "\n".join(out)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("baseline", type=Path, help="Win10 inventory/smoke JSON")
    p.add_argument("pilot", type=Path, help="Win11 inventory/smoke JSON")
    p.add_argument(
        "--json",
        type=Path,
        help="Comparison-JSON output path. Default: "
        "<log_dir>/sdk/compare_<hostname>.json.",
    )
    p.add_argument(
        "--no-json",
        action="store_true",
        help="Do not write the JSON file (print the table only).",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if anything was flagged (CI gate). Off by "
        "default: a flag means review, not fail.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    comparison = build_comparison(load_run(args.baseline), load_run(args.pilot))
    print(render(comparison))

    if not args.no_json:
        payload = build_envelope(
            schema_name=SCHEMA_NAME,
            schema_version=SCHEMA_VERSION,
            machine={"hostname": socket.gethostname(), "role": "comparator"},
            blocks={"comparison": comparison},
            verdict=to_verdict(comparison),
            errors=[],
        )
        host = comparison.get("pilot_machine", {}).get("hostname", "unknown")
        out_path = args.json or (resolved_log_dir("sdk") / f"compare_{host}.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        print(f"Wrote: {out_path}", file=sys.stderr)

    if args.strict and comparison["flags"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
