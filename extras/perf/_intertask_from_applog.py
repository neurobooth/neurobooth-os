"""Inter-task transition timing from log_application (replaces file-time approach).

Pairs STM `FINISHED TASK` / `STARTING TASK` / `End-to-end transition` events
into per-transition rows, optionally augmented with ACQ_0/ACQ_1 `Transition:
device stop/start took ...` attribution.
"""
import re
import sys
from typing import Optional

import pandas as pd
from _db import get_conn

LOG_RE = {
    "starting":     re.compile(r"^STARTING TASK: (\S+)"),
    "finished":     re.compile(r"^FINISHED TASK: (\S+)"),
    "end_to_end":   re.compile(r"^End-to-end transition: ([\d.]+)"),
    "task_wait":    re.compile(r"^Total task WAIT took: ([\d.]+)"),  # available since 2024-11
    "acq_stop":     re.compile(r"^Transition: device stop took ([\d.]+) for (\S+)"),
    "acq_start":    re.compile(r"^Transition: device start took ([\d.]+) for (\S+)"),
    "stm_stop_acq": re.compile(r"^stop_acq took: ([\d.]+)"),
    "stm_wait_acq": re.compile(r"^Waiting for ACQ to start took: ([\d.]+)"),
    "stm_idle":     re.compile(r"^Inter-task gap \(STM idle\): ([\d.]+)"),
}


def fetch_app_log(conn, date_from: str, date_to: str) -> pd.DataFrame:
    q = """
    SELECT session_id, server_id, server_type, server_time, function, message
    FROM log_application
    WHERE server_time::date BETWEEN %s::date AND %s::date
      AND (
        (server_type = 'presentation' AND (
            message LIKE 'STARTING TASK:%%'
         OR message LIKE 'FINISHED TASK:%%'
         OR message LIKE 'End-to-end transition:%%'
         OR message LIKE 'Total task WAIT took:%%'
         OR message LIKE 'stop_acq took:%%'
         OR message LIKE 'Waiting for ACQ to start took:%%'
         OR message LIKE 'Inter-task gap (STM idle):%%'
        ))
        OR
        (server_type = 'acquisition' AND (
            message LIKE 'Transition: device stop took%%'
         OR message LIKE 'Transition: device start took%%'
        ))
      )
    ORDER BY session_id, server_time
    """
    return pd.read_sql_query(q, conn, params=(date_from, date_to))


def pair_events(df: pd.DataFrame) -> pd.DataFrame:
    """Walk per-session events and emit one row per completed transition."""
    rows = []
    for sid, sub in df.groupby("session_id"):
        # State for the in-progress transition
        from_task = None
        from_finished_at = None
        to_task = None
        to_started_at = None
        e2e = None
        e2e_at = None
        task_wait = None
        stop_acq = None
        wait_acq = None
        stm_idle = None
        acq_stops = {}   # server_id -> (seconds, task_id)
        acq_starts = {}

        def emit(emit_at):
            # Use End-to-end if present, else Total task WAIT took
            transition = e2e if e2e is not None else task_wait
            if transition is None or from_task is None or to_task is None:
                return
            rows.append({
                "session_name": sid,
                "from_task": from_task,
                "to_task": to_task,
                "from_finished_at": from_finished_at,
                "to_started_at": to_started_at,
                "transition_at": emit_at,
                "transition_sec": transition,
                "metric": "e2e" if e2e is not None else "task_wait",
                "e2e_sec": e2e,
                "task_wait_sec": task_wait,
                "stm_stop_acq_sec": stop_acq,
                "stm_wait_acq_sec": wait_acq,
                "stm_idle_sec": stm_idle,
                "acq0_stop_sec": acq_stops.get("ACQ_0", (None,))[0],
                "acq0_start_sec": acq_starts.get("ACQ_0", (None,))[0],
                "acq1_stop_sec": acq_stops.get("ACQ_1", (None,))[0],
                "acq1_start_sec": acq_starts.get("ACQ_1", (None,))[0],
            })

        for _, r in sub.iterrows():
            msg = r["message"]
            srv = r["server_type"]
            sid_machine = r["server_id"]

            if srv == "presentation":
                m = LOG_RE["finished"].match(msg)
                if m:
                    # If we have pending state (task_wait or e2e never came in
                    # before, and this FINISHED is the *next* task ending), flush.
                    if to_task is not None and (e2e is not None or task_wait is not None):
                        emit(to_started_at)
                        from_task = to_task = from_finished_at = to_started_at = None
                        e2e = e2e_at = task_wait = stop_acq = wait_acq = stm_idle = None
                        acq_stops, acq_starts = {}, {}
                    from_task = m.group(1)
                    from_finished_at = r["server_time"]
                    continue
                m = LOG_RE["starting"].match(msg)
                if m:
                    to_task = m.group(1)
                    to_started_at = r["server_time"]
                    continue
                m = LOG_RE["end_to_end"].match(msg)
                if m:
                    e2e = float(m.group(1))
                    e2e_at = r["server_time"]
                    emit(e2e_at)
                    from_task = to_task = from_finished_at = to_started_at = None
                    e2e = e2e_at = task_wait = stop_acq = wait_acq = stm_idle = None
                    acq_stops, acq_starts = {}, {}
                    continue
                m = LOG_RE["task_wait"].match(msg)
                if m:
                    task_wait = float(m.group(1))
                    # If End-to-end never arrives (older code), emit on next FINISHED
                    continue
                m = LOG_RE["stm_stop_acq"].match(msg)
                if m:
                    stop_acq = float(m.group(1)); continue
                m = LOG_RE["stm_wait_acq"].match(msg)
                if m:
                    wait_acq = float(m.group(1)); continue
                m = LOG_RE["stm_idle"].match(msg)
                if m:
                    stm_idle = float(m.group(1)); continue

            elif srv == "acquisition":
                m = LOG_RE["acq_stop"].match(msg)
                if m:
                    acq_stops[sid_machine] = (float(m.group(1)), m.group(2))
                    continue
                m = LOG_RE["acq_start"].match(msg)
                if m:
                    acq_starts[sid_machine] = (float(m.group(1)), m.group(2))
                    continue

    return pd.DataFrame(rows)


def add_session_metadata(conn, df: pd.DataFrame, date_from: str, date_to: str) -> pd.DataFrame:
    """Join to log_session and drop test-subject sessions.

    Mirrors `intertask_report.fetch_session_data`'s `lt.subject_id > '100001'`
    filter (string comparison; works for 6-digit numeric subject_ids).
    """
    if df.empty:
        return df
    sn_q = """
    SELECT log_session_id, subject_id, date::text AS date
    FROM log_session
    WHERE date BETWEEN %s::date AND %s::date
      AND subject_id > '100001'
    """
    sn = pd.read_sql_query(sn_q, conn, params=(date_from, date_to))
    sn["session_name"] = sn["subject_id"].astype(str) + "_" + sn["date"]
    sn["date_dt"] = pd.to_datetime(sn["date"])
    # inner join: transitions whose session_name isn't in the filtered set
    # (test subjects, missing log_session) are dropped.
    return df.merge(sn[["session_name", "log_session_id", "date_dt"]],
                    on="session_name", how="inner")


def monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Per-month aggregate: session counts, session-median stats, transition stats."""
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["month"] = df["date_dt"].dt.to_period("M").astype(str)
    # First, per-session medians
    sess = df.groupby(["log_session_id", "month"])["transition_sec"].agg(
        n_transitions="count", session_median="median", session_mean="mean", session_max="max",
    ).reset_index()
    out = sess.groupby("month").agg(
        n_sessions=("log_session_id", "count"),
        median_of_session_medians=("session_median", "median"),
        mean_of_session_medians=("session_median", "mean"),
        std_of_session_medians=("session_median", "std"),
        median_session_mean=("session_mean", "median"),
        median_session_max=("session_max", "median"),
    ).round(2).reset_index()
    # Total transitions per month + metric mix (e2e vs task_wait fallback)
    tx = df.groupby("month")["transition_sec"].agg(n_transitions="count",
                                                    transition_median="median",
                                                    transition_mean="mean").round(2).reset_index()
    metric_mix = df.groupby(["month", "metric"]).size().unstack(fill_value=0)
    metric_mix.columns = [f"n_{c}" for c in metric_mix.columns]
    out = out.merge(tx, on="month").merge(metric_mix.reset_index(), on="month", how="left")
    return out


def main(date_from: str, date_to: str):
    conn, tunnel = get_conn()
    try:
        print(f"Fetching log_application rows for {date_from}..{date_to}")
        events = fetch_app_log(conn, date_from, date_to)
        print(f"  {len(events)} relevant rows")
        if events.empty:
            return
        tx = pair_events(events)
        n_pre = len(tx)
        print(f"  Paired into {n_pre} transitions")
        tx = add_session_metadata(conn, tx, date_from, date_to)
        print(f"  After test-subject filter (subject_id > '100001'): {len(tx)} "
              f"({n_pre - len(tx)} dropped)")
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()

    if tx.empty:
        print("No transitions paired.")
        return

    summ = monthly_summary(tx)
    print("\n=== Monthly summary ===")
    with pd.option_context("display.width", 220, "display.max_rows", 50):
        print(summ.to_string(index=False))

    # Optional: write per-transition CSV for downstream use
    out_csv = "intertask_from_applog.csv"
    tx.to_csv(out_csv, index=False)
    print(f"\nPer-transition CSV: {out_csv}")


if __name__ == "__main__":
    if len(sys.argv) >= 3:
        main(sys.argv[1], sys.argv[2])
    else:
        print("Usage: python _intertask_from_applog.py YYYY-MM-DD YYYY-MM-DD")
        sys.exit(2)
