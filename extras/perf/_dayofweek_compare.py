"""Compare inter-task gaps across days of the week.

Uses intertask_report's compute_transition_gaps over a date range, then
aggregates per session (median per session) and groups by day-of-week.
"""
import sys
import pandas as pd
import intertask_report as ir
from _db import get_conn

DATE_FROM = "2026-03-01"
DATE_TO   = "2026-04-30"


def main(date_from: str = DATE_FROM, date_to: str = DATE_TO):
    conn, tunnel = get_conn()
    try:
        df = ir.fetch_session_data(conn, date_from=date_from, date_to=date_to)
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()
    print(f"Fetched {len(df)} rows across {df['log_session_id'].nunique()} sessions, "
          f"{date_from} to {date_to}.")
    if df.empty:
        return
    gaps = ir.compute_transition_gaps(df)
    if gaps.empty:
        print("No gaps computed.")
        return
    print(f"{len(gaps)} transitions across {gaps['session_id'].nunique()} sessions.")

    gaps["session_date"] = pd.to_datetime(gaps["session_date"])
    gaps["dow"] = gaps["session_date"].dt.day_name()

    # Per-session medians
    sess = gaps.groupby(["session_id", "session_date", "dow"])["max_gap"].agg(
        n="count", session_median="median", session_mean="mean", session_max="max",
    ).reset_index()

    DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    sess["dow"] = pd.Categorical(sess["dow"], categories=DOW_ORDER, ordered=True)
    sess = sess.sort_values(["session_date", "session_id"])

    # Aggregate per day-of-week (median of session medians)
    print("\n=== Day-of-week aggregate (session-median inter-task gap, sec) ===")
    dow_agg = sess.groupby("dow", observed=True).agg(
        n_sessions=("session_id", "count"),
        median_of_session_medians=("session_median", "median"),
        mean_of_session_medians=("session_median", "mean"),
        std_of_session_medians=("session_median", "std"),
        median_session_mean=("session_mean", "median"),
    ).round(2)
    print(dow_agg.to_string())

    # Distribution table — list each session's median grouped by DOW
    print("\n=== Session medians by day-of-week ===")
    for dow in DOW_ORDER:
        sub = sess[sess["dow"] == dow]
        if sub.empty:
            continue
        vals = sub["session_median"].round(1).tolist()
        print(f"  {dow:9s} (n={len(sub):2d}): "
              f"med={sub['session_median'].median():4.1f}  "
              f"mean={sub['session_median'].mean():4.1f}  "
              f"min={sub['session_median'].min():4.1f}  "
              f"max={sub['session_median'].max():4.1f}  "
              f"  values={vals}")

    # Per-transition by DOW: median across sessions, for the in-vs-out comparison
    print("\n=== Per-transition median (sec), by day-of-week ===")
    pt = gaps.groupby(["from_pos", "from_task", "to_task", "dow"],
                      observed=True)["max_gap"].median().reset_index()
    pt["dow"] = pd.Categorical(pt["dow"], categories=DOW_ORDER, ordered=True)
    pivot = pt.pivot_table(index=["from_pos", "from_task", "to_task"],
                           columns="dow", values="max_gap", observed=True)
    pivot = pivot.sort_index(level="from_pos")
    pivot.index = pivot.index.to_frame(index=False).apply(
        lambda r: f"{int(r['from_pos']):2d} {r['from_task'][:22]} -> {r['to_task'][:22]}", axis=1)
    cols_order = [d for d in DOW_ORDER if d in pivot.columns]
    pivot = pivot[cols_order]
    with pd.option_context("display.max_colwidth", 60, "display.width", 240,
                           "display.max_rows", 50):
        print(pivot.round(1).to_string())

    # Add bottom row: median across all transitions, per DOW
    overall = gaps.groupby("dow", observed=True)["max_gap"].median().round(2)
    print(f"\nOverall median across all transitions per DOW:")
    print(overall.to_string())


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) >= 2:
        main(args[0], args[1])
    elif len(args) == 1:
        main(args[0], args[0])
    else:
        main()
