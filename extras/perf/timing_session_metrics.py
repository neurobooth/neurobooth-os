"""Win10 vs Win11 timing A/B from already-collected session data.

Strategy doc (``docs/timing_test_strategy.md``) **Test D**: every real
clinical session already records the timing signal, so the cheapest
regression instrument for #759 concern #3 (issue #761) reads it back
remotely -- no lab, no recording, no booth time.

Two clearly separated tiers, by design (strategy §6.1: "the risk is the
metric math, not the plumbing"):

* **Tier 1 -- implemented here.** Metrics that are genuinely derivable from
  Postgres and follow patterns this repo already proves: per-device
  cross-device **start skew**, **marker -> first-sample latency**, and
  per-device **coarse recording span**, all from ``log_sensor_file`` /
  ``log_task`` / ``log_session`` exactly as ``intertask_report.py`` queries
  them. The Win10/Win11 split generalizes the single ``CUTOVER`` date in
  ``mbient_timing_before_after.py`` to explicit *baseline* and *pilot* date
  windows (the #759 phased plan: a locked historical Win10 window, then a
  later Win11-pilot window, with an allowed gap between).

* **Tier 2 -- scaffolded, NOT computed here.** Sample-level frame-interval
  jitter, native-vs-LSL clock **drift (ppm)**, and dropped/duplicated-frame
  detection. Those need the *per-sample* timestamps, which live in the
  per-device **HDF5** files (``Time_RealSense``/``Time_ACQ``,
  ``Time_FLIR``, ``Time_iPhone`` -- see the device ``StreamInfo`` columns),
  **not in Postgres**. They are also new, unproven metric definitions; a
  subtly wrong one yields confident, wrong A/B deltas. Per the strategy
  doc they are gated behind a methodology review before any number is
  trusted, so this tool emits an explicit ``deferred`` sentinel for them
  rather than a fabricated value.

The live database path mirrors ``intertask_report.py`` and
``mbient_timing_before_after.py`` column-for-column; it has not been run
against the production DB from a dev machine. The pure transform layer
(period assignment, skew/latency/span, A/B summary) is unit-tested on
synthetic frames.

Usage::

    uv run python extras/perf/timing_session_metrics.py \\
        --baseline-from 2025-09-20 --baseline-to 2026-03-03 \\
        --pilot-from 2026-03-15 --pilot-to 2026-05-15 \\
        [--study study1] [--collection mvp_030] [--min-subject 100001] \\
        [--json extras/perf/baselines/timing/session_ab.json] [--stdout]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from _baseline_common import CollectionError, build_envelope, collect_os_identity

SCHEMA_VERSION = 1
SCHEMA_NAME = "timing_session_metrics"

# Per-device, per-task start/end times. Column-for-column the same shape as
# intertask_report.fetch_session_data so we inherit a query this repo has
# already exercised against production. Study/collection/min-subject are
# parameterized rather than hard-coded.
SESSION_FILES_SQL = """
SELECT
    lsf.device_id,
    lt.log_session_id,
    ls.date AS session_date,
    lt.task_id,
    MIN(lsf.file_start_time) AS task_start,
    MAX(lsf.file_end_time)   AS task_end
FROM log_sensor_file lsf
JOIN log_task    lt ON lsf.log_task_id   = lt.log_task_id
JOIN log_session ls ON lt.log_session_id = ls.log_session_id
WHERE ls.study_id = %(study)s
  AND ls.collection_id = %(collection)s
  AND lt.subject_id > %(min_subject)s
  AND lsf.file_start_time IS NOT NULL
  AND ls.date >= %(date_from)s
  AND ls.date <= %(date_to)s
GROUP BY lsf.device_id, lt.log_session_id, ls.date, lt.task_id, lt.log_task_id
ORDER BY lt.log_session_id, lsf.device_id, MIN(lsf.file_start_time)
"""

# The LSL marker stream is recorded as a device row like any other; this is
# the device_id it lands under. Used for marker -> first-sample latency.
MARKER_DEVICE_ID = "Marker"

# ---------------------------------------------------------------------------
# Tier 2 -- scaffolded only. See module docstring and strategy §6.1.
# ---------------------------------------------------------------------------

SAMPLE_LEVEL_DEFERRED: Dict[str, Any] = {
    "status": "deferred",
    "reason": (
        "Per-sample jitter / native-vs-LSL drift / dropped-duplicated-frame "
        "detection require the per-device HDF5 sample timestamps, which are "
        "NOT in Postgres, and are new metric definitions that must pass a "
        "methodology review before any number is trusted."
    ),
    "data_source": (
        "per-device HDF5: Time_RealSense/Time_ACQ (Intel), Time_FLIR (FLIR), "
        "Time_iPhone/Time_ACQ (iPhone), plus the LSL timestamp column"
    ),
    "tracked_by": "issue #761; docs/timing_test_strategy.md §6.1",
    "metrics_pending": [
        "frame_interval_mean_sd_p95_p99",
        "native_vs_lsl_clock_drift_ppm",
        "dropped_frame_count_and_rate",
        "duplicated_sample_count",
    ],
}

_REVIEW_MSG = (
    "Tier-2 sample-level metric: deferred pending the methodology review "
    "required by docs/timing_test_strategy.md §6.1. The data source is the "
    "per-device HDF5 sample timestamps, not Postgres -- implementing this "
    "against the DB would silently produce wrong A/B deltas."
)


def frame_interval_jitter_from_hdf5(*_args: Any, **_kwargs: Any) -> None:
    """Scaffold: per-device frame-interval jitter from HDF5. Not implemented."""
    raise NotImplementedError(_REVIEW_MSG)


def native_vs_lsl_drift_ppm_from_hdf5(*_args: Any, **_kwargs: Any) -> None:
    """Scaffold: native-vs-LSL clock drift (ppm) from HDF5. Not implemented."""
    raise NotImplementedError(_REVIEW_MSG)


def dropped_duplicated_frames_from_hdf5(*_args: Any, **_kwargs: Any) -> None:
    """Scaffold: dropped/duplicated-frame detection from HDF5. Not implemented."""
    raise NotImplementedError(_REVIEW_MSG)


# ---------------------------------------------------------------------------
# Tier 1 -- pure transform layer (unit-tested on synthetic frames)
# ---------------------------------------------------------------------------


def assign_period(
    df: pd.DataFrame,
    baseline: Tuple[str, str],
    pilot: Tuple[str, str],
) -> pd.DataFrame:
    """Tag each row ``baseline`` / ``pilot`` / ``None`` by ``session_date``.

    Generalizes the single ``CUTOVER`` in ``mbient_timing_before_after.py``
    to two explicit, possibly non-adjacent windows so a locked Win10 window
    and a later Win11-pilot window can be compared with a deliberate gap
    between them (rows in the gap are excluded, not silently bucketed).

    Args:
        df: Must contain a ``session_date`` column (date or ISO string).
        baseline: ``(from, to)`` inclusive ISO dates for the Win10 window.
        pilot: ``(from, to)`` inclusive ISO dates for the Win11 window.

    Returns:
        A copy of ``df`` with a new ``period`` column.
    """
    out = df.copy()
    sd = out["session_date"].astype(str)

    def _bucket(d: str) -> Optional[str]:
        if baseline[0] <= d <= baseline[1]:
            return "baseline"
        if pilot[0] <= d <= pilot[1]:
            return "pilot"
        return None

    out["period"] = sd.map(_bucket)
    return out


def start_skew(df: pd.DataFrame) -> pd.DataFrame:
    """Cross-device start skew per (session, task).

    Skew = ``max(task_start) - min(task_start)`` across all devices that
    recorded that task. Large skew means devices did not start together (a
    G1 cross-device-sync regression signal).

    Args:
        df: Rows with ``log_session_id``, ``task_id``, ``task_start``,
            ``session_date``, and (if present) ``period``.

    Returns:
        One row per (session, task) with ``skew_sec`` and ``n_devices``.
    """
    g = df.groupby(["log_session_id", "task_id"], as_index=False).agg(
        session_date=("session_date", "first"),
        period=("period", "first") if "period" in df else ("task_id", "size"),
        first_start=("task_start", "min"),
        last_start=("task_start", "max"),
        n_devices=("device_id", "nunique"),
    )
    g["skew_sec"] = (
        pd.to_datetime(g["last_start"]) - pd.to_datetime(g["first_start"])
    ).dt.total_seconds()
    return g.drop(columns=["first_start", "last_start"])


def marker_first_sample_latency(df: pd.DataFrame) -> pd.DataFrame:
    """Latency from the Marker stream start to the first device sample.

    Per (session, task): ``min(non-marker device task_start) -
    marker task_start``. Sessions/tasks without a Marker row are skipped
    (no baseline to measure against), which is reported, not hidden.

    Args:
        df: Rows including the marker device (``device_id == "Marker"``).

    Returns:
        One row per (session, task) with ``marker_latency_sec``.
    """
    rows: List[Dict[str, Any]] = []
    for (sid, task), grp in df.groupby(["log_session_id", "task_id"]):
        marker = grp[grp["device_id"] == MARKER_DEVICE_ID]
        others = grp[grp["device_id"] != MARKER_DEVICE_ID]
        if marker.empty or others.empty:
            continue
        m_start = pd.to_datetime(marker["task_start"]).min()
        first_sample = pd.to_datetime(others["task_start"]).min()
        rows.append(
            {
                "log_session_id": sid,
                "task_id": task,
                "session_date": grp["session_date"].iloc[0],
                "period": grp["period"].iloc[0] if "period" in grp else None,
                "marker_latency_sec": (first_sample - m_start).total_seconds(),
            }
        )
    return pd.DataFrame(rows)


def device_span(df: pd.DataFrame) -> pd.DataFrame:
    """Per-device coarse recording span (``task_end - task_start``) per task.

    Coarse by construction -- this is file-level start/end, not per-sample.
    It is a stable, DB-derivable proxy for "did this device record for the
    expected duration"; the fine-grained jitter view is the deferred Tier-2
    work.

    Args:
        df: Rows with ``task_start`` and ``task_end``.

    Returns:
        ``df`` plus a ``span_sec`` column.
    """
    out = df.copy()
    out["span_sec"] = (
        pd.to_datetime(out["task_end"]) - pd.to_datetime(out["task_start"])
    ).dt.total_seconds()
    return out


def summarize(series: "pd.Series") -> Dict[str, Optional[float]]:
    """Distribution summary (mirrors the ``ps()`` helper in the perf scripts).

    Args:
        series: Numeric values.

    Returns:
        ``{n, mean, median, sd, p25, p75, p95, min, max}``; all-but-``n``
        are ``None`` for an empty series.
    """
    s = series.dropna()
    if len(s) == 0:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "sd": None,
            "p25": None,
            "p75": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    return {
        "n": int(len(s)),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "sd": float(s.std(ddof=0)),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
        "p95": float(s.quantile(0.95)),
        "min": float(s.min()),
        "max": float(s.max()),
    }


def ab_summary(df: pd.DataFrame, value_col: str) -> Dict[str, Any]:
    """Baseline vs pilot distribution + raw delta for one metric.

    Always reports both distributions and the raw mean/median deltas; it
    never collapses them to a pass/fail (the strategy doc is explicit:
    "Flag means a human looks, not fail").

    Args:
        df: Must contain ``period`` and ``value_col``.
        value_col: The metric column to summarize.

    Returns:
        ``{baseline, pilot, delta}`` where ``delta`` is pilot-minus-baseline
        for ``mean`` and ``median`` (``None`` if either side is empty).
    """
    base = summarize(df.loc[df["period"] == "baseline", value_col])
    pilot = summarize(df.loc[df["period"] == "pilot", value_col])

    def _d(key: str) -> Optional[float]:
        if base[key] is None or pilot[key] is None:
            return None
        return float(pilot[key] - base[key])

    return {
        "baseline": base,
        "pilot": pilot,
        "delta": {"mean": _d("mean"), "median": _d("median")},
    }


# ---------------------------------------------------------------------------
# Live DB path (mirrors intertask_report.py / mbient_timing_before_after.py)
# ---------------------------------------------------------------------------


def fetch_session_files(
    conn: Any,
    study: str,
    collection: str,
    min_subject: str,
    date_from: str,
    date_to: str,
) -> pd.DataFrame:
    """Run :data:`SESSION_FILES_SQL`. Spans the full baseline+pilot range."""
    return pd.read_sql_query(
        SESSION_FILES_SQL,
        conn,
        params={
            "study": study,
            "collection": collection,
            "min_subject": min_subject,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


def compute_metrics(
    df: pd.DataFrame,
    baseline: Tuple[str, str],
    pilot: Tuple[str, str],
) -> Dict[str, Any]:
    """Assemble the Tier-1 A/B metric block from a fetched frame.

    Pure given ``df``; this is the seam the unit tests drive with synthetic
    data so the metric math is covered without a database.
    """
    tagged = assign_period(df, baseline, pilot)
    tagged = tagged[tagged["period"].notna()]

    skew = start_skew(tagged)
    latency = marker_first_sample_latency(tagged)
    spans = device_span(tagged)

    per_device_span: Dict[str, Any] = {}
    for dev, grp in spans.groupby("device_id"):
        per_device_span[str(dev)] = ab_summary(grp, "span_sec")

    n_base_sessions = int(
        tagged.loc[tagged["period"] == "baseline", "log_session_id"].nunique()
    )
    n_pilot_sessions = int(
        tagged.loc[tagged["period"] == "pilot", "log_session_id"].nunique()
    )

    return {
        "windows": {
            "baseline": {"from": baseline[0], "to": baseline[1]},
            "pilot": {"from": pilot[0], "to": pilot[1]},
        },
        "session_counts": {
            "baseline": n_base_sessions,
            "pilot": n_pilot_sessions,
        },
        "cross_device_start_skew_sec": ab_summary(skew, "skew_sec"),
        "marker_to_first_sample_latency_sec": (
            ab_summary(latency, "marker_latency_sec")
            if not latency.empty
            else {
                "baseline": summarize(pd.Series([], dtype=float)),
                "pilot": summarize(pd.Series([], dtype=float)),
                "delta": {"mean": None, "median": None},
                "note": "no Marker device rows in range",
            }
        ),
        "per_device_recording_span_sec": per_device_span,
        "sample_level": SAMPLE_LEVEL_DEFERRED,
    }


def _print_ab(title: str, block: Dict[str, Any]) -> None:
    """Render one ab_summary block as the familiar perf-script text table."""
    print(f"\n  {title}")
    for period in ("baseline", "pilot"):
        s = block[period]
        if s["n"] == 0:
            print(f"    {period:8s}: No data")
            continue
        print(
            f"    {period:8s}: Mean {s['mean']:.3f}s  Median {s['median']:.3f}s"
            f"  SD {s['sd']:.3f}s  p95 {s['p95']:.3f}s  N={s['n']}"
        )
    d = block.get("delta", {})
    if d.get("mean") is not None:
        print(f"    delta   : mean {d['mean']:+.3f}s  median {d['median']:+.3f}s")


def print_report(metrics: Dict[str, Any]) -> None:
    """Human A/B report, same UX as the other ``extras/perf`` scripts."""
    w = metrics["windows"]
    sc = metrics["session_counts"]
    print("=" * 75)
    print("TIMING SESSION METRICS -- Win10 baseline vs Win11 pilot (Test D)")
    print(
        f"  baseline {w['baseline']['from']}..{w['baseline']['to']} "
        f"({sc['baseline']} sessions)   "
        f"pilot {w['pilot']['from']}..{w['pilot']['to']} "
        f"({sc['pilot']} sessions)"
    )
    print("=" * 75)
    _print_ab("Cross-device start skew", metrics["cross_device_start_skew_sec"])
    _print_ab(
        "Marker -> first-sample latency",
        metrics["marker_to_first_sample_latency_sec"],
    )
    print("\n  Per-device coarse recording span (baseline -> pilot mean):")
    for dev, blk in sorted(metrics["per_device_recording_span_sec"].items()):
        b, p = blk["baseline"], blk["pilot"]
        bm = f"{b['mean']:.2f}s" if b["n"] else "n/a"
        pm = f"{p['mean']:.2f}s" if p["n"] else "n/a"
        print(f"    {dev:24s}  {bm:>9s} -> {pm:>9s}")
    print(
        "\n  Sample-level jitter/drift/drops: "
        f"{metrics['sample_level']['status'].upper()} "
        f"({metrics['sample_level']['tracked_by']})"
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--baseline-from", required=True, help="Win10 window start (YYYY-MM-DD)"
    )
    p.add_argument("--baseline-to", required=True, help="Win10 window end (YYYY-MM-DD)")
    p.add_argument(
        "--pilot-from", required=True, help="Win11 window start (YYYY-MM-DD)"
    )
    p.add_argument("--pilot-to", required=True, help="Win11 window end (YYYY-MM-DD)")
    p.add_argument("--study", default="study1", help="study_id (default: study1)")
    p.add_argument(
        "--collection", default="mvp_030", help="collection_id (default: mvp_030)"
    )
    p.add_argument(
        "--min-subject",
        default="100001",
        help="Exclude subject_id <= this (default: 100001, drops test subjects)",
    )
    p.add_argument(
        "--json",
        type=Path,
        help="Also write the metric block as a baseline-envelope JSON.",
    )
    p.add_argument(
        "--stdout", action="store_true", help="Print the JSON envelope to stdout."
    )
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    baseline = (args.baseline_from, args.baseline_to)
    pilot = (args.pilot_from, args.pilot_to)
    full_from = min(args.baseline_from, args.pilot_from)
    full_to = max(args.baseline_to, args.pilot_to)

    errors: List[CollectionError] = []
    machine, os_errors = collect_os_identity(None)
    errors.extend(os_errors)

    # _db is imported lazily: the pure transform layer (and its tests) must
    # not require psycopg2 / sshtunnel just to import this module.
    from _db import get_conn

    conn, tunnel = get_conn()
    try:
        df = fetch_session_files(
            conn,
            args.study,
            args.collection,
            args.min_subject,
            full_from,
            full_to,
        )
    finally:
        conn.close()
        tunnel.stop()

    print(
        f"Fetched {len(df)} device-task rows across "
        f"{df['log_session_id'].nunique() if not df.empty else 0} sessions.",
        file=sys.stderr,
    )

    metrics = compute_metrics(df, baseline, pilot)
    print_report(metrics)

    if args.json or args.stdout:
        verdict = {
            "category": "CAPTURED",
            "reasons": [
                "Tier-1 DB-derived A/B. Sample-level jitter/drift/drops are "
                "deferred (see metrics.sample_level).",
                "Calendar-window A/B confounds OS with subjects/room/drivers/"
                "release (strategy §6.1.2); treat as the representative "
                "corroborator, not the causal instrument.",
            ],
            "remediation_hints": [],
        }
        payload = build_envelope(
            schema_name=SCHEMA_NAME,
            schema_version=SCHEMA_VERSION,
            machine=machine,
            blocks={"metrics": metrics},
            verdict=verdict,
            errors=errors,
        )
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(
                json.dumps(payload, indent=2, default=str), encoding="utf-8"
            )
            print(f"Wrote: {args.json}", file=sys.stderr)
        if args.stdout:
            print(json.dumps(payload, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
