"""Pivot of app-log inter-task transitions: rows=transitions, cols=sessions.

Reads intertask_from_applog.csv (produced by _intertask_from_applog.py) and
prints a transition x session pivot plus per-session max.
"""
import sys
from pathlib import Path

import pandas as pd
import intertask_report as ir

CSV = "intertask_from_applog.csv"


def main(csv_path: str = CSV) -> None:
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows from {csv_path}")

    df["from_pos"] = df["from_task"].map(ir.TASK_INDEX)
    df["to_pos"] = df["to_task"].map(ir.TASK_INDEX)
    valid = df.dropna(subset=["from_pos", "to_pos"]).copy()
    valid = valid[valid["to_pos"] == valid["from_pos"] + 1].copy()
    valid["from_pos"] = valid["from_pos"].astype(int)
    print(f"Filtered to {len(valid)} canonical adjacent transitions "
          f"across {valid['session_name'].nunique()} sessions.")

    pivot = valid.pivot_table(
        index=["from_pos", "from_task", "to_task"],
        columns="session_name",
        values="transition_sec",
        aggfunc="first",
    ).sort_index(level="from_pos").round(1)

    pivot.index = pivot.index.to_frame(index=False).apply(
        lambda r: f"{int(r['from_pos']):2d} {r['from_task'][:24]} -> {r['to_task'][:24]}",
        axis=1,
    )

    with pd.option_context("display.width", 260, "display.max_rows", 60,
                           "display.max_colwidth", 200):
        print("\n=== Inter-task transition_sec: rows=transition, cols=session ===")
        print(pivot.to_string())

        print("\n=== Per-session max (sec) ===")
        sess_max = (valid.groupby("session_name")["transition_sec"]
                    .agg(n="count", median="median", mean="mean", max="max")
                    .round(2)
                    .sort_values("max", ascending=False))
        print(sess_max.to_string())

        # Identify which transition produced the per-session max
        idx = valid.groupby("session_name")["transition_sec"].idxmax()
        max_rows = valid.loc[idx, ["session_name", "from_pos", "from_task",
                                    "to_task", "transition_sec"]]
        max_rows = max_rows.sort_values("transition_sec", ascending=False)
        max_rows["transition"] = max_rows.apply(
            lambda r: f"{int(r['from_pos']):2d} {r['from_task'][:24]} -> {r['to_task'][:24]}",
            axis=1,
        )
        print("\n=== Where the max came from ===")
        print(max_rows[["session_name", "transition_sec", "transition"]]
              .to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else CSV)
