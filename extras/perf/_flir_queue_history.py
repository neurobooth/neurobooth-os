"""FLIR save-thread queue-buildup history from log_application.

Aggregates `Queue length is N frame count: M` messages across sessions to
expose how often the FLIR save thread falls behind the camera, which tasks
are running at peak queue, and whether buildup was already underway before
the cognitive trigger tasks (MOT_obs_1, DSC_obs, hevelius_obs).

Background and motivating analysis: neurobooth/neurobooth-os#775.

Usage:
    python _flir_queue_history.py                         # last 12 months
    python _flir_queue_history.py --from 2025-01-01 --to 2026-05-01
    python _flir_queue_history.py --csv peaks.csv         # also write per-session CSV
"""
import argparse
import re
import sys
from typing import List, Optional

import pandas as pd
from _db import get_conn

QUEUE_RE = re.compile(r"^Queue length is (\d+)\s+frame count:\s*(\d+)")
START_RE = re.compile(r"^STARTING TASK: (\S+)")
E2E_RE = re.compile(r"^End-to-end transition:\s*([\d.]+)")

# Tasks that historically dominate peak-queue events.
TRIGGER_TASKS = ("MOT_obs_1", "DSC_obs", "hevelius_obs")

SEVERITY_ORDER = [
    "catastrophic (>=5000)",
    "severe (1000-4999)",
    "moderate (200-999)",
    "minor (50-199)",
    "normal (<50)",
]


def severity(q: int) -> str:
    """Bucket a peak queue depth into a severity label."""
    if q >= 5000:
        return SEVERITY_ORDER[0]
    if q >= 1000:
        return SEVERITY_ORDER[1]
    if q >= 200:
        return SEVERITY_ORDER[2]
    if q >= 50:
        return SEVERITY_ORDER[3]
    return SEVERITY_ORDER[4]


def fetch_queue_samples(conn, date_from: Optional[str], date_to: Optional[str]) -> pd.DataFrame:
    """Pull all Queue-length messages in the date range, parsed into (q, frame)."""
    where = ["message LIKE 'Queue length is%%'", "session_id <> ''"]
    params: List = []
    if date_from:
        where.append("server_time >= %s::timestamptz")
        params.append(date_from)
    if date_to:
        where.append("server_time <= %s::timestamptz")
        params.append(date_to)
    q = f"""
    SELECT session_id, server_time, message
    FROM log_application
    WHERE {' AND '.join(where)}
    """
    df = pd.read_sql_query(q, conn, params=params)
    df["server_time"] = pd.to_datetime(df["server_time"], utc=True)
    parsed = df["message"].str.extract(QUEUE_RE).astype(float)
    df["q"] = parsed[0]
    df["frame"] = parsed[1]
    df = df.dropna(subset=["q"]).copy()
    df["q"] = df["q"].astype(int)
    df["frame"] = df["frame"].astype(int)
    df["date"] = pd.to_datetime(
        df["session_id"].str.extract(r"_(\d{4}-\d{2}-\d{2})$")[0], errors="coerce"
    )
    return df.dropna(subset=["date"])


def fetch_task_context(conn, sessions: List[str]) -> pd.DataFrame:
    """Pull STARTING TASK and End-to-end transition rows for the given sessions."""
    if not sessions:
        return pd.DataFrame(columns=["session_id", "server_time", "kind", "val"])
    q = """
    SELECT session_id, server_time, message
    FROM log_application
    WHERE session_id = ANY(%s)
      AND (message LIKE 'STARTING TASK:%%' OR message LIKE 'End-to-end transition:%%')
    """
    df = pd.read_sql_query(q, conn, params=(sessions,))
    df["server_time"] = pd.to_datetime(df["server_time"], utc=True)
    start_match = df["message"].str.extract(START_RE)[0]
    e2e_match = df["message"].str.extract(E2E_RE)[0]
    df["kind"] = pd.NA
    df.loc[start_match.notna(), "kind"] = "start"
    df.loc[e2e_match.notna(), "kind"] = "e2e"
    df["val"] = start_match.fillna(e2e_match)
    return df.dropna(subset=["kind"])


def session_peaks(samples: pd.DataFrame, starts: pd.DataFrame) -> pd.DataFrame:
    """Per-session peak queue depth and the task running when the peak occurred."""
    peak = (samples.sort_values("q", ascending=False)
            .drop_duplicates("session_id")
            [["session_id", "date", "server_time", "q", "frame"]]
            .reset_index(drop=True))

    # For each peak, find the most recent STARTING TASK before its server_time.
    starts_sorted = (starts[starts["kind"].eq("start")]
                     .sort_values("server_time"))
    tasks: List[Optional[str]] = []
    for _, r in peak.iterrows():
        s = starts_sorted[(starts_sorted.session_id == r["session_id"])
                          & (starts_sorted.server_time <= r["server_time"])]
        tasks.append(s.iloc[-1]["val"] if len(s) else None)
    peak["task_at_peak"] = tasks
    peak["severity"] = peak["q"].apply(severity)
    peak["month"] = peak["date"].dt.to_period("M").astype(str)
    return peak


def pre_trigger_buildup(samples: pd.DataFrame, starts: pd.DataFrame,
                        peak: pd.DataFrame) -> pd.DataFrame:
    """For sessions whose peak occurred at a TRIGGER_TASKS task, was the queue
    already growing before that task started?"""
    cat = peak[(peak["q"] >= 5000) & peak["task_at_peak"].isin(TRIGGER_TASKS)].copy()
    if cat.empty:
        return pd.DataFrame()

    trig_starts = (starts[starts["kind"].eq("start") & starts["val"].isin(TRIGGER_TASKS)]
                   .sort_values("server_time")
                   .drop_duplicates("session_id", keep="first")
                   [["session_id", "server_time", "val"]]
                   .rename(columns={"server_time": "trigger_start", "val": "trigger_task"}))
    joined = samples.merge(trig_starts, on="session_id", how="inner")
    pre = joined[joined.server_time < joined.trigger_start]
    pre_max = (pre.groupby("session_id")["q"].max()
               .rename("pre_trigger_max_q").reset_index())
    out = cat.merge(pre_max, on="session_id", how="left")
    out["pre_trigger_max_q"] = out["pre_trigger_max_q"].fillna(0).astype(int)
    out["pre_trigger_bucket"] = out["pre_trigger_max_q"].apply(severity)
    return out


def session_max_e2e(starts: pd.DataFrame) -> pd.DataFrame:
    """Per-session maximum End-to-end transition value (seconds)."""
    e2e = starts[starts["kind"].eq("e2e")].copy()
    if e2e.empty:
        return pd.DataFrame(columns=["session_id", "max_transition_sec"])
    e2e["sec"] = e2e["val"].astype(float)
    return (e2e.groupby("session_id")["sec"].max()
            .rename("max_transition_sec").reset_index())


def report(peak: pd.DataFrame, pre: pd.DataFrame, e2e: pd.DataFrame, top_n: int = 10) -> None:
    """Print the standard summary report."""
    print(f"\n=== {len(peak)} sessions, "
          f"{peak['date'].min().date()} .. {peak['date'].max().date()} ===")

    # Monthly severity matrix
    mix = (peak.groupby(["month", "severity"]).size()
           .unstack(fill_value=0)
           .reindex(columns=[c for c in SEVERITY_ORDER if c in
                             peak["severity"].unique()]))
    mix["total"] = mix.sum(axis=1)
    print("\n=== Severity by month ===")
    with pd.option_context("display.width", 200):
        print(mix.to_string())

    # Top sessions
    print(f"\n=== Top {top_n} sessions by peak queue ===")
    cols = ["session_id", "date", "q", "frame", "task_at_peak"]
    top = peak.sort_values("q", ascending=False).head(top_n)[cols].copy()
    top["date"] = top["date"].dt.date
    print(top.to_string(index=False))

    # Task at peak
    print("\n=== Task running at peak queue ===")
    by_task = (peak.groupby("task_at_peak", dropna=False)
               .agg(n=("q", "count"),
                    n_catastrophic=("q", lambda s: int((s >= 5000).sum())),
                    median=("q", "median"),
                    max=("q", "max"))
               .sort_values("n", ascending=False))
    print(by_task.to_string())

    # Pre-trigger buildup analysis
    if not pre.empty:
        print(f"\n=== Pre-trigger buildup: catastrophic-at-{','.join(TRIGGER_TASKS)} sessions ===")
        print(f"{len(pre)} sessions where peak occurred at a trigger task.")
        bucket_counts = pre["pre_trigger_bucket"].value_counts().reindex(
            [b for b in SEVERITY_ORDER if b in pre["pre_trigger_bucket"].unique()],
            fill_value=0)
        bucket_pct = (bucket_counts / len(pre) * 100).round(0).astype(int)
        summary = pd.DataFrame({"n": bucket_counts, "%": bucket_pct})
        print(summary.to_string())
        threshold_200 = (pre["pre_trigger_max_q"] >= 200).mean() * 100
        print(f"\n{threshold_200:.0f}% had pre-trigger queue >= 200 frames "
              f"(buildup already underway before the cognitive task started).")

    # Correlation with inter-task stalls (where e2e data is available)
    if not e2e.empty:
        merged = peak.merge(e2e, on="session_id", how="inner")
        if not merged.empty:
            print(f"\n=== Peak queue vs longest inter-task transition ({len(merged)} sessions) ===")
            buckets = pd.cut(merged["q"], bins=[-1, 49, 199, 999, 4999, 999999],
                             labels=["<50", "50-199", "200-999", "1000-4999", ">=5000"])
            g = (merged.groupby(buckets, observed=True)["max_transition_sec"]
                 .agg(n="count", median="median",
                      p75=lambda s: s.quantile(0.75), max="max")
                 .round(1))
            print(g.to_string())
            corr = merged[["q", "max_transition_sec"]].corr().iloc[0, 1]
            print(f"\nPearson correlation (peak_q, max_transition_sec): {corr:.3f}")


def main(date_from: Optional[str], date_to: Optional[str],
         csv_out: Optional[str], top_n: int) -> None:
    conn, tunnel = get_conn()
    try:
        print(f"Fetching log_application Queue rows for "
              f"{date_from or 'last 12mo'} .. {date_to or 'today'}")
        samples = fetch_queue_samples(conn, date_from, date_to)
        print(f"  {len(samples)} samples across {samples.session_id.nunique()} sessions")
        if samples.empty:
            return
        starts = fetch_task_context(conn, samples.session_id.unique().tolist())
        print(f"  {len(starts)} task-context rows fetched")
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()

    peak = session_peaks(samples, starts)
    pre = pre_trigger_buildup(samples, starts, peak)
    e2e = session_max_e2e(starts)
    report(peak, pre, e2e, top_n=top_n)

    if csv_out:
        out = peak.copy()
        if not pre.empty:
            out = out.merge(pre[["session_id", "pre_trigger_max_q",
                                  "pre_trigger_bucket"]],
                            on="session_id", how="left")
        if not e2e.empty:
            out = out.merge(e2e, on="session_id", how="left")
        out.to_csv(csv_out, index=False)
        print(f"\nWrote per-session CSV: {csv_out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--from", dest="date_from", default=None,
                   help="Start date YYYY-MM-DD (default: last 12 months)")
    p.add_argument("--to", dest="date_to", default=None,
                   help="End date YYYY-MM-DD (default: today)")
    p.add_argument("--csv", dest="csv_out", default=None,
                   help="Optional path to write per-session CSV")
    p.add_argument("--top", dest="top_n", type=int, default=10,
                   help="Top N sessions to list (default: 10)")
    args = p.parse_args()

    if args.date_from is None and args.date_to is None:
        # Default: last 12 months
        args.date_from = (pd.Timestamp.utcnow() - pd.DateOffset(months=12)).date().isoformat()

    main(args.date_from, args.date_to, args.csv_out, args.top_n)
