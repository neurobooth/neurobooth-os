"""Diff two timing baselines (Win10 locked vs Win11 pilot) into a delta table.

Strategy doc (``docs/timing_test_strategy.md``) §4 piece 3 / §6: ingest two
``timing_baseline.py`` artefacts and emit *every* raw delta, then derive a
verdict from the numbers. The numbers are authoritative; the verdict is a
convenience so a glance tells you whether something moved.

Design rules taken verbatim from the strategy doc:

* **Raw deltas are always printed**, for every metric, whether or not any
  threshold trips. Nothing is hidden behind a boolean.
* The thresholds below are **proposals to be ratified by whoever owns the
  timing budget -- not measured facts.** They are named constants and every
  one is CLI-overridable.
* A tripped threshold means **"flag: a human looks, with the numbers in
  hand"** -- never an automatic "fail". The process exits 0 even when
  flagged, unless ``--strict`` is given (for callers that want a hard gate).

Pure stdlib (json/argparse/pathlib/socket): no DB, no pandas, no PsychoPy,
so it runs anywhere and is fully unit-testable.

Usage::

    uv run python extras/perf/compare_timing.py \\
        extras/perf/baselines/timing/win10/stm.json \\
        extras/perf/baselines/timing/win11/stm.json \\
        [--sd-regression-ratio 1.25] [--p99-ratio 2.0] \\
        [--json delta.json] [--strict]
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from _baseline_common import build_envelope

SCHEMA_VERSION = 1
SCHEMA_NAME = "timing_comparison"

# --- Proposed thresholds (strategy §6). NOT measured facts. CLI-overridable.
# A trip means "a human looks", not "fail".
DEFAULT_SD_REGRESSION_RATIO = 1.25  # jitter SD regression > 25% vs baseline
DEFAULT_P99_RATIO = 2.0  # microbench p99 worse by > 2x baseline
DEFAULT_MAX_NEW_DROPPED = 0  # new dropped flips where baseline had ~none

# Below this (seconds / count) a baseline value is "effectively zero", so a
# ratio is meaningless and we fall back to an absolute "new regression" rule.
_EPS = 1e-9

_MICROBENCH_STATS = ("mean", "sd", "p95", "p99", "max")


def load_baseline(path: Path) -> Dict[str, Any]:
    """Read and JSON-parse one baseline artefact.

    Raises:
        FileNotFoundError / json.JSONDecodeError: surfaced to the caller; a
        comparator that silently swallowed a bad input would be worse than
        one that stops.
    """
    return json.loads(path.read_text(encoding="utf-8"))


def _ratio(base: Optional[float], pilot: Optional[float]) -> Optional[float]:
    """``pilot / base`` or ``None`` when base is missing / ~zero."""
    if base is None or pilot is None or abs(base) <= _EPS:
        return None
    return pilot / base


def _delta(base: Optional[float], pilot: Optional[float]) -> Optional[float]:
    """``pilot - base`` or ``None`` if either side is missing."""
    if base is None or pilot is None:
        return None
    return pilot - base


def _cmp_scalar(
    base: Optional[float], pilot: Optional[float]
) -> Dict[str, Optional[float]]:
    """Raw comparison cell: baseline, pilot, delta, ratio (no judgement)."""
    return {
        "baseline": base,
        "pilot": pilot,
        "delta": _delta(base, pilot),
        "ratio": _ratio(base, pilot),
    }


def _os_label(machine: Dict[str, Any]) -> str:
    """Human OS label from a ``machine`` block."""
    cap = machine.get("os_caption")
    build = machine.get("os_build")
    if cap and build:
        return f"{cap} (build {build})"
    return str(cap or build or "unknown")


def compare_microbench(
    base_mb: Dict[str, Any],
    pilot_mb: Dict[str, Any],
    sd_ratio_limit: float,
    p99_ratio_limit: float,
) -> Tuple[Dict[str, Any], List[str]]:
    """Per-primitive raw deltas + SD/p99 regression flags.

    Args:
        base_mb: ``metrics.microbench`` from the baseline artefact.
        pilot_mb: same from the pilot artefact.
        sd_ratio_limit: Flag if ``pilot.sd / baseline.sd`` exceeds this.
        p99_ratio_limit: Flag if ``pilot.p99 / baseline.p99`` exceeds this.

    Returns:
        ``(table, flags)`` -- ``table`` keeps every stat for every primitive;
        ``flags`` are human-readable lines for the verdict.
    """
    table: Dict[str, Any] = {}
    flags: List[str] = []
    all_primitives = sorted(set(base_mb) | set(pilot_mb))

    for prim in all_primitives:
        b = base_mb.get(prim) or {}
        p = pilot_mb.get(prim) or {}
        if not b or not p:
            table[prim] = {
                "status": "not_comparable",
                "reason": f"missing in {'baseline' if not b else 'pilot'}",
            }
            flags.append(
                f"microbench '{prim}': present in only one artefact "
                f"-- not comparable."
            )
            continue

        cell = {s: _cmp_scalar(b.get(s), p.get(s)) for s in _MICROBENCH_STATS}

        sd_r = cell["sd"]["ratio"]
        sd_b, sd_p = b.get("sd"), p.get("sd")
        if sd_r is not None and sd_r > sd_ratio_limit:
            cell["sd"]["flagged"] = True
            flags.append(
                f"microbench '{prim}' jitter SD x{sd_r:.2f} "
                f"({sd_b:.3e}s -> {sd_p:.3e}s) > x{sd_ratio_limit} proposed."
            )
        elif (
            sd_r is None
            and (sd_b is not None and abs(sd_b) <= _EPS)
            and (sd_p is not None and sd_p > _EPS)
        ):
            cell["sd"]["flagged"] = True
            flags.append(
                f"microbench '{prim}' jitter SD rose from ~0 to {sd_p:.3e}s "
                f"(baseline effectively zero)."
            )

        p99_r = cell["p99"]["ratio"]
        p99_b, p99_p = b.get("p99"), p.get("p99")
        if p99_r is not None and p99_r > p99_ratio_limit:
            cell["p99"]["flagged"] = True
            flags.append(
                f"microbench '{prim}' p99 x{p99_r:.2f} "
                f"({p99_b:.3e}s -> {p99_p:.3e}s) > x{p99_ratio_limit} proposed."
            )

        table[prim] = cell

    return table, flags


def compare_flip_stats(
    base_fs: Optional[Dict[str, Any]],
    pilot_fs: Optional[Dict[str, Any]],
    sd_ratio_limit: float,
    max_new_dropped: int,
) -> Tuple[Dict[str, Any], List[str]]:
    """Flip-jitter raw deltas + SD-regression and new-dropped-flip flags.

    The flip probe is optional, so either side may be absent; that is
    reported as ``not_comparable`` (with a reason), never silently passed.
    """
    if not base_fs or not pilot_fs:
        which = "baseline" if not base_fs else "pilot"
        return (
            {
                "status": "not_comparable",
                "reason": f"flip_stats absent in {which} "
                f"(optional --with-flip-stats probe)",
            },
            [],
        )

    flags: List[str] = []
    fields = ("mean_ms", "sd_ms", "p95_ms", "p99_ms", "max_ms")
    table: Dict[str, Any] = {
        f: _cmp_scalar(base_fs.get(f), pilot_fs.get(f)) for f in fields
    }
    table["dropped_flips"] = _cmp_scalar(
        base_fs.get("dropped_flips"), pilot_fs.get("dropped_flips")
    )
    table["requested_hz"] = _cmp_scalar(
        base_fs.get("requested_hz"), pilot_fs.get("requested_hz")
    )

    sd_r = table["sd_ms"]["ratio"]
    if sd_r is not None and sd_r > sd_ratio_limit:
        table["sd_ms"]["flagged"] = True
        flags.append(
            f"flip-interval jitter SD x{sd_r:.2f} "
            f"({base_fs.get('sd_ms'):.3f}ms -> {pilot_fs.get('sd_ms'):.3f}ms) "
            f"> x{sd_ratio_limit} proposed."
        )

    b_drop = base_fs.get("dropped_flips") or 0
    p_drop = pilot_fs.get("dropped_flips") or 0
    if b_drop <= max_new_dropped and p_drop > max_new_dropped:
        table["dropped_flips"]["flagged"] = True
        flags.append(
            f"dropped flips rose {b_drop} -> {p_drop} "
            f"(baseline within proposed {max_new_dropped})."
        )

    return table, flags


def build_comparison(
    baseline: Dict[str, Any],
    pilot: Dict[str, Any],
    *,
    sd_ratio_limit: float = DEFAULT_SD_REGRESSION_RATIO,
    p99_ratio_limit: float = DEFAULT_P99_RATIO,
    max_new_dropped: int = DEFAULT_MAX_NEW_DROPPED,
) -> Dict[str, Any]:
    """Assemble the full structured comparison. Pure; the unit-test seam.

    Args:
        baseline: Parsed Win10 ``timing_baseline`` artefact.
        pilot: Parsed Win11 ``timing_baseline`` artefact.
        sd_ratio_limit: Proposed jitter-SD regression ratio.
        p99_ratio_limit: Proposed microbench-p99 regression ratio.
        max_new_dropped: Proposed tolerated dropped-flip baseline.

    Returns:
        A JSON-serializable comparison: schema check, OS transition, every
        raw delta, the thresholds used, and the human ``flags`` list.
    """
    b_machine = baseline.get("machine", {})
    p_machine = pilot.get("machine", {})

    schema_ok = baseline.get("schema_name") == pilot.get("schema_name") == (
        "timing_baseline"
    ) and baseline.get("schema_version") == pilot.get("schema_version")

    flags: List[str] = []
    if not schema_ok:
        flags.append(
            "schema mismatch: "
            f"{baseline.get('schema_name')}/v{baseline.get('schema_version')} "
            f"vs {pilot.get('schema_name')}/v{pilot.get('schema_version')} "
            "-- comparing overlapping fields only."
        )

    b_metrics = baseline.get("metrics", {})
    p_metrics = pilot.get("metrics", {})

    mb_table, mb_flags = compare_microbench(
        b_metrics.get("microbench", {}),
        p_metrics.get("microbench", {}),
        sd_ratio_limit,
        p99_ratio_limit,
    )
    fs_table, fs_flags = compare_flip_stats(
        b_metrics.get("flip_stats"),
        p_metrics.get("flip_stats"),
        sd_ratio_limit,
        max_new_dropped,
    )
    flags += mb_flags + fs_flags

    interval_b = b_metrics.get("requested_interval_s")
    interval_p = p_metrics.get("requested_interval_s")
    if interval_b != interval_p:
        flags.append(
            f"requested microbench interval differs "
            f"({interval_b}s baseline vs {interval_p}s pilot) -- ratios still "
            f"shown but compare with care."
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
            "pilot": (f"{pilot.get('schema_name')}" f"/v{pilot.get('schema_version')}"),
            "compatible": bool(schema_ok),
        },
        "thresholds": {
            "sd_regression_ratio": sd_ratio_limit,
            "p99_ratio": p99_ratio_limit,
            "max_new_dropped": max_new_dropped,
            "_note": (
                "proposals to be ratified by the timing-budget owner, "
                "not measured facts (strategy doc §6)"
            ),
        },
        "microbench": mb_table,
        "flip_stats": fs_table,
        "flags": flags,
    }


def to_verdict(comparison: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the convenience verdict. ``REVIEW`` if anything was flagged.

    Never ``FAIL``. The standing first reason restates that thresholds are
    proposals and that a flag means a human looks.
    """
    flags = comparison.get("flags", [])
    reasons = [
        "Thresholds are proposals (strategy §6), not measured facts. A flag "
        "means a human reviews with the numbers in hand -- not a failure.",
    ]
    reasons += flags
    return {
        "category": "REVIEW" if flags else "MATCH",
        "reasons": reasons,
        "remediation_hints": (
            [
                "Inspect the flagged metrics in the delta table; re-run the "
                "pilot on an idle booth if a single run looks contaminated."
            ]
            if flags
            else []
        ),
    }


def _fmt(v: Optional[float]) -> str:
    """Compact fixed/scientific formatting for the text table."""
    if v is None:
        return "    n/a"
    if v == 0:
        return "  0.000"
    if abs(v) < 1e-3 or abs(v) >= 1e5:
        return f"{v:.3e}"
    return f"{v:.4f}"


def render(comparison: Dict[str, Any]) -> str:
    """Render the comparison as the familiar perf-script text table."""
    out: List[str] = []
    ot = comparison["os_transition"]
    out.append("=" * 78)
    out.append("TIMING COMPARISON  --  Win10 baseline -> Win11 pilot")
    out.append(f"  {ot['from']}  ->  {ot['to']}")
    if not comparison["schema"]["compatible"]:
        out.append(
            f"  SCHEMA: {comparison['schema']['baseline']} vs "
            f"{comparison['schema']['pilot']}  (overlap only)"
        )
    out.append("=" * 78)

    out.append("\nMicrobench -- absolute error vs requested interval (seconds)")
    hdr = f"  {'primitive':<20s}{'stat':<6s}{'baseline':>12s}{'pilot':>12s}{'delta':>12s}{'ratio':>9s}"
    out.append(hdr)
    out.append("  " + "-" * (len(hdr) - 2))
    for prim, cell in comparison["microbench"].items():
        if cell.get("status") == "not_comparable":
            out.append(f"  {prim:<20s}(not comparable: {cell['reason']})")
            continue
        for stat in _MICROBENCH_STATS:
            c = cell[stat]
            r = c.get("ratio")
            rs = f"{r:>8.2f}x" if r is not None else "     n/a"
            flag = "  <== FLAG" if c.get("flagged") else ""
            out.append(
                f"  {prim:<20s}{stat:<6s}{_fmt(c['baseline']):>12s}"
                f"{_fmt(c['pilot']):>12s}{_fmt(c['delta']):>12s}{rs:>9s}{flag}"
            )

    out.append("\nFlip-interval jitter (milliseconds)")
    fs = comparison["flip_stats"]
    if fs.get("status") == "not_comparable":
        out.append(f"  (not comparable: {fs['reason']})")
    else:
        for k, c in fs.items():
            r = c.get("ratio")
            rs = f"{r:>8.2f}x" if r is not None else "     n/a"
            flag = "  <== FLAG" if c.get("flagged") else ""
            out.append(
                f"  {k:<16s}{_fmt(c['baseline']):>12s}"
                f"{_fmt(c['pilot']):>12s}{_fmt(c['delta']):>12s}{rs:>9s}{flag}"
            )

    verdict = to_verdict(comparison)
    out.append(f"\nVERDICT: {verdict['category']}")
    for r in verdict["reasons"]:
        out.append(f"  - {r}")
    out.append("")
    return "\n".join(out)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("baseline", type=Path, help="Win10 timing_baseline JSON")
    p.add_argument("pilot", type=Path, help="Win11 timing_baseline JSON")
    p.add_argument(
        "--sd-regression-ratio",
        type=float,
        default=DEFAULT_SD_REGRESSION_RATIO,
        help=f"Proposed jitter-SD regression ratio "
        f"(default {DEFAULT_SD_REGRESSION_RATIO}).",
    )
    p.add_argument(
        "--p99-ratio",
        type=float,
        default=DEFAULT_P99_RATIO,
        help=f"Proposed microbench-p99 regression ratio "
        f"(default {DEFAULT_P99_RATIO}).",
    )
    p.add_argument(
        "--max-new-dropped",
        type=int,
        default=DEFAULT_MAX_NEW_DROPPED,
        help=f"Tolerated baseline dropped-flip count before a rise is "
        f"flagged (default {DEFAULT_MAX_NEW_DROPPED}).",
    )
    p.add_argument(
        "--json", type=Path, help="Also write the comparison as an envelope JSON."
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if anything was flagged (for hard CI gates). "
        "Off by default: a flag means review, not fail.",
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    baseline = load_baseline(args.baseline)
    pilot = load_baseline(args.pilot)

    comparison = build_comparison(
        baseline,
        pilot,
        sd_ratio_limit=args.sd_regression_ratio,
        p99_ratio_limit=args.p99_ratio,
        max_new_dropped=args.max_new_dropped,
    )
    print(render(comparison))

    if args.json:
        verdict = to_verdict(comparison)
        payload = build_envelope(
            schema_name=SCHEMA_NAME,
            schema_version=SCHEMA_VERSION,
            machine={"hostname": socket.gethostname(), "role": "comparator"},
            blocks={"comparison": comparison},
            verdict=verdict,
            errors=[],
        )
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        print(f"Wrote: {args.json}", file=sys.stderr)

    if args.strict and comparison["flags"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
