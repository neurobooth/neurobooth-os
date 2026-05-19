"""Diff two Mbient soak runs (Win10 locked vs Win11 pilot) into a delta table.

Sibling of ``compare_timing.py`` for #762 / #759 concern #4. Ingests two
``mbient_soak.py`` artefacts and emits *every* raw delta, then derives a
verdict from the numbers.

Design rules, identical to the timing comparator (strategy doc §6):

* **Raw deltas are always printed**, for every metric, flagged or not.
* The thresholds are **proposals to be ratified by whoever owns the BLE
  budget -- not measured facts.** Named constants, every one CLI-overridable.
* A trip means **"a human looks, with the numbers in hand"** -- never an
  automatic fail. Exit 0 even when flagged, unless ``--strict``.
* The single most important signal is **the native-crash transition**: a
  Win11 run that no longer crashes is only meaningful if the iPhone
  co-runner state matches (the #669 measurement trap) -- this tool surfaces
  that pairing rather than hiding it behind a green check.

Pure stdlib (json/argparse/pathlib/socket): no DB, no neurobooth stack, so
it runs anywhere and is fully unit-testable.

Usage::

    uv run python extras/perf/mbient_soak_compare.py \\
        extras/perf/baselines/mbient_soak/win10/acq.json \\
        extras/perf/baselines/mbient_soak/win11/acq.json \\
        [--p95-ratio 1.25] [--drop-rate-increase 0.05] \\
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
SCHEMA_NAME = "mbient_soak_comparison"
# The schema_name the soak artefacts carry, distinct from this comparator's
# own SCHEMA_NAME.
SCHEMA_NAME_SRC = "mbient_soak"

# --- Proposed thresholds (NOT measured facts). CLI-overridable. Flag != fail.
DEFAULT_P95_RATIO = 1.25  # connect/reset p95 worse by > 25% vs baseline
DEFAULT_DROP_RATE_INCREASE = 0.05  # mean drop-rate up > 5 percentage points
DEFAULT_OK_FRACTION_DROP = 0.05  # ok-fraction down > 5 percentage points

_EPS = 1e-9
# (metric path, stat) pairs compared as scalars with a ratio.
_RATIO_METRICS = (
    ("connect_ms", "mean"),
    ("connect_ms", "p95"),
    ("reset_ms", "mean"),
    ("reset_ms", "p95"),
)


def load_run(path: Path) -> Dict[str, Any]:
    """Read and JSON-parse one soak artefact (surfaced errors, not swallowed)."""
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(base: Optional[float], pilot: Optional[float]) -> Optional[float]:
    if base is None or pilot is None or abs(base) <= _EPS:
        return None
    return pilot / base


def _delta(base: Optional[float], pilot: Optional[float]) -> Optional[float]:
    if base is None or pilot is None:
        return None
    return pilot - base


def _cell(base: Optional[float], pilot: Optional[float]) -> Dict[str, Any]:
    return {
        "baseline": base,
        "pilot": pilot,
        "delta": _delta(base, pilot),
        "ratio": _ratio(base, pilot),
    }


def _os_label(machine: Dict[str, Any]) -> str:
    cap = machine.get("os_caption")
    build = machine.get("os_build")
    if cap and build:
        return f"{cap} (build {build})"
    return str(cap or build or "unknown")


def build_comparison(
    baseline: Dict[str, Any],
    pilot: Dict[str, Any],
    *,
    p95_ratio_limit: float = DEFAULT_P95_RATIO,
    drop_rate_increase: float = DEFAULT_DROP_RATE_INCREASE,
    ok_fraction_drop: float = DEFAULT_OK_FRACTION_DROP,
) -> Dict[str, Any]:
    """Assemble the full structured comparison. Pure; the unit-test seam."""
    b_machine = baseline.get("machine", {})
    p_machine = pilot.get("machine", {})
    bm = baseline.get("metrics", {})
    pm = pilot.get("metrics", {})
    b_run = baseline.get("run", {})
    p_run = pilot.get("run", {})
    b_crash = baseline.get("crash", {})
    p_crash = pilot.get("crash", {})

    flags: List[str] = []

    schema_ok = baseline.get("schema_name") == pilot.get(
        "schema_name"
    ) == SCHEMA_NAME_SRC and baseline.get("schema_version") == pilot.get(
        "schema_version"
    )
    if not schema_ok:
        flags.append(
            "schema mismatch: "
            f"{baseline.get('schema_name')}/v{baseline.get('schema_version')} "
            f"vs {pilot.get('schema_name')}/v{pilot.get('schema_version')} "
            "-- comparing overlapping fields only."
        )

    # Scalar latency metrics (connect/reset mean+p95) with ratio flagging.
    latency: Dict[str, Any] = {}
    for metric, stat in _RATIO_METRICS:
        b = (bm.get(metric) or {}).get(stat)
        p = (pm.get(metric) or {}).get(stat)
        cell = _cell(b, p)
        r = cell["ratio"]
        if r is not None and r > p95_ratio_limit:
            cell["flagged"] = True
            flags.append(
                f"{metric}.{stat} x{r:.2f} ({b:.1f}ms -> {p:.1f}ms) "
                f"> x{p95_ratio_limit} proposed."
            )
        elif (
            r is None
            and (b is not None and abs(b) <= _EPS)
            and (p is not None and p > _EPS)
        ):
            cell["flagged"] = True
            flags.append(f"{metric}.{stat} rose from ~0 to {p:.1f}ms.")
        latency[f"{metric}.{stat}"] = cell

    # Drop-rate (mean): an increase beyond the proposed band is flagged.
    b_drop = (bm.get("drop_rate") or {}).get("mean")
    p_drop = (pm.get("drop_rate") or {}).get("mean")
    drop_cell = _cell(b_drop, p_drop)
    if drop_cell["delta"] is not None and drop_cell["delta"] > drop_rate_increase:
        drop_cell["flagged"] = True
        flags.append(
            f"mean sample drop-rate +{drop_cell['delta']:.1%} "
            f"({b_drop:.1%} -> {p_drop:.1%}) > "
            f"{drop_rate_increase:.0%} proposed."
        )

    # ok-fraction: a drop beyond the proposed band is flagged.
    b_ok = bm.get("ok_fraction")
    p_ok = pm.get("ok_fraction")
    ok_cell = _cell(b_ok, p_ok)
    if ok_cell["delta"] is not None and ok_cell["delta"] < -ok_fraction_drop:
        ok_cell["flagged"] = True
        flags.append(
            f"ok-fraction {b_ok:.1%} -> {p_ok:.1%} "
            f"(down > {ok_fraction_drop:.0%} proposed)."
        )

    # BLE disconnects: any new ones where the baseline had none is flagged.
    b_disc = bm.get("ble_disconnects_total")
    p_disc = pm.get("ble_disconnects_total")
    disc_cell = _cell(b_disc, p_disc)
    if (b_disc == 0 or b_disc is None) and (p_disc or 0) > 0:
        disc_cell["flagged"] = True
        flags.append(f"BLE disconnects rose 0 -> {p_disc} (baseline had none).")

    # The crash transition -- the headline signal, paired with co-runner state.
    b_crashed = bool(b_crash.get("crashed"))
    p_crashed = bool(p_crash.get("crashed"))
    b_iphone = b_run.get("iphone_corunner")
    p_iphone = p_run.get("iphone_corunner")
    crash_block = {
        "baseline": {
            "crashed": b_crashed,
            "exit_code_hex": b_crash.get("exit_code_hex"),
            "iphone_corunner": b_iphone,
        },
        "pilot": {
            "crashed": p_crashed,
            "exit_code_hex": p_crash.get("exit_code_hex"),
            "iphone_corunner": p_iphone,
        },
        "iphone_corunner_match": b_iphone == p_iphone,
    }
    if b_crashed and not p_crashed:
        if b_iphone == p_iphone:
            crash_block["interpretation"] = (
                "Win11 did not crash where Win10 did, iPhone co-runner state "
                "matched -- promising, but the co-runner is synthetic so this "
                "is suggestive, not definitive (#669)."
            )
        else:
            crash_block["flagged"] = True
            flags.append(
                f"crash improved (Win10 crashed, Win11 did not) BUT iPhone "
                f"co-runner differed ({b_iphone} vs {p_iphone}) -- the #669 "
                f"measurement trap; result is not comparable."
            )
    elif p_crashed and not b_crashed:
        crash_block["flagged"] = True
        flags.append(
            f"REGRESSION: Win11 crashed where Win10 did not "
            f"(exit {p_crash.get('exit_code_hex')})."
        )
    elif b_crashed and p_crashed:
        crash_block["interpretation"] = (
            "Both crashed -- compare crash.dump_paths / faulthandler stacks "
            "to see if it is the same native signature."
        )

    return {
        "baseline_machine": b_machine,
        "pilot_machine": p_machine,
        "os_transition": {
            "from": _os_label(b_machine),
            "to": _os_label(p_machine),
        },
        "schema": {
            "baseline": (
                f"{baseline.get('schema_name')}" f"/v{baseline.get('schema_version')}"
            ),
            "pilot": (f"{pilot.get('schema_name')}/v{pilot.get('schema_version')}"),
            "compatible": bool(schema_ok),
        },
        "thresholds": {
            "p95_ratio": p95_ratio_limit,
            "drop_rate_increase": drop_rate_increase,
            "ok_fraction_drop": ok_fraction_drop,
            "_note": (
                "proposals to be ratified by the BLE-budget owner, not "
                "measured facts"
            ),
        },
        "latency": latency,
        "drop_rate_mean": drop_cell,
        "ok_fraction": ok_cell,
        "ble_disconnects_total": disc_cell,
        "crash": crash_block,
        "flags": flags,
    }


def to_verdict(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience verdict. ``REVIEW`` if anything flagged; never ``FAIL``."""
    flags = comparison.get("flags", [])
    reasons = [
        "Thresholds are proposals (not measured facts). A flag means a human "
        "reviews with the numbers in hand -- not a failure. The iPhone "
        "co-runner is synthetic, so crash-improvement is suggestive (#669).",
    ]
    reasons += flags
    return {
        "category": "REVIEW" if flags else "MATCH",
        "reasons": reasons,
        "remediation_hints": (
            [
                "Inspect the flagged metrics; for a crash delta confirm the "
                "iPhone co-runner state matched and compare native stacks."
            ]
            if flags
            else []
        ),
    }


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "    n/a"
    if v == 0:
        return "  0.000"
    if abs(v) < 1e-3 or abs(v) >= 1e5:
        return f"{v:.3e}"
    return f"{v:.3f}"


def render(comparison: Dict[str, Any]) -> str:
    """Render the comparison as the familiar perf-script text table."""
    out: List[str] = []
    ot = comparison["os_transition"]
    out.append("=" * 78)
    out.append("MBIENT SOAK COMPARISON  --  Win10 baseline -> Win11 pilot")
    out.append(f"  {ot['from']}  ->  {ot['to']}")
    if not comparison["schema"]["compatible"]:
        out.append(
            f"  SCHEMA: {comparison['schema']['baseline']} vs "
            f"{comparison['schema']['pilot']}  (overlap only)"
        )
    out.append("=" * 78)

    out.append("\nLatency (ms)")
    hdr = (
        f"  {'metric':<18s}{'baseline':>12s}{'pilot':>12s}"
        f"{'delta':>12s}{'ratio':>9s}"
    )
    out.append(hdr)
    out.append("  " + "-" * (len(hdr) - 2))
    for name, c in comparison["latency"].items():
        r = c.get("ratio")
        rs = f"{r:>8.2f}x" if r is not None else "     n/a"
        flag = "  <== FLAG" if c.get("flagged") else ""
        out.append(
            f"  {name:<18s}{_fmt(c['baseline']):>12s}{_fmt(c['pilot']):>12s}"
            f"{_fmt(c['delta']):>12s}{rs:>9s}{flag}"
        )

    for label, key in (
        ("drop_rate (mean)", "drop_rate_mean"),
        ("ok_fraction", "ok_fraction"),
        ("ble_disconnects", "ble_disconnects_total"),
    ):
        c = comparison[key]
        flag = "  <== FLAG" if c.get("flagged") else ""
        out.append(
            f"\n  {label:<18s}{_fmt(c['baseline']):>12s} -> "
            f"{_fmt(c['pilot']):>12s}  (delta {_fmt(c['delta'])}){flag}"
        )

    cb = comparison["crash"]
    out.append("\nCrash transition")
    out.append(
        f"  baseline: crashed={cb['baseline']['crashed']} "
        f"({cb['baseline']['exit_code_hex']}) "
        f"iphone={cb['baseline']['iphone_corunner']}"
    )
    out.append(
        f"  pilot:    crashed={cb['pilot']['crashed']} "
        f"({cb['pilot']['exit_code_hex']}) "
        f"iphone={cb['pilot']['iphone_corunner']}"
    )
    if cb.get("interpretation"):
        out.append(f"  -> {cb['interpretation']}")

    verdict = to_verdict(comparison)
    out.append(f"\nVERDICT: {verdict['category']}")
    for r in verdict["reasons"]:
        out.append(f"  - {r}")
    out.append("")
    return "\n".join(out)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("baseline", type=Path, help="Win10 mbient_soak JSON")
    p.add_argument("pilot", type=Path, help="Win11 mbient_soak JSON")
    p.add_argument(
        "--p95-ratio",
        type=float,
        default=DEFAULT_P95_RATIO,
        help=f"Proposed connect/reset p95 regression ratio "
        f"(default {DEFAULT_P95_RATIO}).",
    )
    p.add_argument(
        "--drop-rate-increase",
        type=float,
        default=DEFAULT_DROP_RATE_INCREASE,
        help=f"Proposed tolerated mean drop-rate increase "
        f"(default {DEFAULT_DROP_RATE_INCREASE}).",
    )
    p.add_argument(
        "--ok-fraction-drop",
        type=float,
        default=DEFAULT_OK_FRACTION_DROP,
        help=f"Proposed tolerated ok-fraction drop "
        f"(default {DEFAULT_OK_FRACTION_DROP}).",
    )
    p.add_argument(
        "--json",
        type=Path,
        help="Comparison-JSON output path. Default: "
        "<log_dir>/mbient_soak/compare_<hostname>.json.",
    )
    p.add_argument(
        "--no-json",
        action="store_true",
        help="Do not write the JSON file (print the delta table only).",
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
    baseline = load_run(args.baseline)
    pilot = load_run(args.pilot)

    comparison = build_comparison(
        baseline,
        pilot,
        p95_ratio_limit=args.p95_ratio,
        drop_rate_increase=args.drop_rate_increase,
        ok_fraction_drop=args.ok_fraction_drop,
    )
    print(render(comparison))

    if not args.no_json:
        verdict = to_verdict(comparison)
        payload = build_envelope(
            schema_name=SCHEMA_NAME,
            schema_version=SCHEMA_VERSION,
            machine={"hostname": socket.gethostname(), "role": "comparator"},
            blocks={"comparison": comparison},
            verdict=verdict,
            errors=[],
        )
        host = comparison.get("pilot_machine", {}).get("hostname", "unknown")
        out_path = args.json or (
            resolved_log_dir("mbient_soak") / f"compare_{host}.json"
        )
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
