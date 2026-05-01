"""Pivot of intertask_report gaps: rows=transitions, cols=sessions."""
import sys
from datetime import date, timedelta
import pandas as pd
import intertask_report as ir

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

def main(target_date: str = YESTERDAY) -> None:
    conn = ir.get_connection_direct()
    try:
        df = ir.fetch_session_data(conn, date_from=target_date, date_to=target_date)
    finally:
        conn.close()
        ir.cleanup()
    print(f"Fetched {len(df)} rows for {target_date}; "
          f"{df['log_session_id'].nunique()} sessions.")
    if df.empty:
        return
    gaps = ir.compute_transition_gaps(df)
    if gaps.empty:
        print("No valid gaps computed.")
        return

    pivot = gaps.pivot_table(
        index=["from_pos", "from_task", "to_task"],
        columns="session_id",
        values="max_gap",
        aggfunc="first",
    ).sort_index(level="from_pos")

    transition_lbl = pivot.index.to_frame(index=False).apply(
        lambda r: f"{int(r['from_pos']):2d} {r['from_task'][:24]} -> {r['to_task'][:24]}",
        axis=1,
    )
    pivot.index = transition_lbl

    long_pole = gaps.pivot_table(
        index=["from_pos", "from_task", "to_task"],
        columns="session_id",
        values="long_pole_device",
        aggfunc="first",
    ).sort_index(level="from_pos")

    fmt = pivot.copy().astype(object)
    for col in fmt.columns:
        for idx_orig, idx_lbl in zip(long_pole.index, pivot.index):
            v = pivot.loc[idx_lbl, col]
            d = long_pole.loc[idx_orig, col]
            if pd.isna(v):
                fmt.loc[idx_lbl, col] = "    -    "
            else:
                short = "" if pd.isna(d) else str(d).replace("Mbient_", "Mb_").replace("_dev_1", "")[:9]
                fmt.loc[idx_lbl, col] = f"{v:5.1f} {short}"

    with pd.option_context("display.max_colwidth", 200, "display.width", 240,
                           "display.max_rows", 100):
        print(f"\n=== Inter-task gaps for {target_date} (sec, with long-pole device) ===")
        print(fmt.to_string())

        print("\n=== Per-session summary ===")
        sess_summary = gaps.groupby("session_id")["max_gap"].agg(
            n="count", mean="mean", median="median", max="max",
        ).round(1)
        print(sess_summary.to_string())

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else YESTERDAY)
