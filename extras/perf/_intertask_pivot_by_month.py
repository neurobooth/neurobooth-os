"""Per-transition median (rows) by month (cols), from app-log CSV."""
import pandas as pd
import intertask_report as ir

CSV = "intertask_from_applog.csv"


def main():
    df = pd.read_csv(CSV)
    print(f"Loaded {len(df)} rows from {CSV}")

    # Filter to MVP30 transitions in canonical order
    df["from_pos"] = df["from_task"].map(ir.TASK_INDEX)
    df["to_pos"]   = df["to_task"].map(ir.TASK_INDEX)
    valid = df.dropna(subset=["from_pos", "to_pos"]).copy()
    # Keep only adjacent canonical transitions (to_pos == from_pos + 1)
    valid = valid[valid["to_pos"] == valid["from_pos"] + 1].copy()
    valid["from_pos"] = valid["from_pos"].astype(int)
    print(f"Filtered to {len(valid)} canonical adjacent transitions.")

    valid["date_dt"] = pd.to_datetime(valid["date_dt"])
    valid["month"] = valid["date_dt"].dt.to_period("M").astype(str)

    pivot = valid.pivot_table(
        index=["from_pos", "from_task", "to_task"],
        columns="month", values="transition_sec", aggfunc="median",
    ).sort_index(level="from_pos").round(1)

    n_pivot = valid.pivot_table(
        index=["from_pos", "from_task", "to_task"],
        columns="month", values="transition_sec", aggfunc="count",
    ).sort_index(level="from_pos")

    pivot.index = pivot.index.to_frame(index=False).apply(
        lambda r: f"{int(r['from_pos']):2d} {r['from_task'][:25]} -> {r['to_task'][:25]}",
        axis=1,
    )

    print("\n=== Per-transition median (sec), by month ===")
    with pd.option_context("display.width", 240, "display.max_rows", 60,
                           "display.max_colwidth", 200):
        print(pivot.to_string())

    print("\n=== Sample size n per cell ===")
    n_pivot.index = pivot.index
    with pd.option_context("display.width", 240, "display.max_rows", 60):
        print(n_pivot.to_string())


if __name__ == "__main__":
    main()
