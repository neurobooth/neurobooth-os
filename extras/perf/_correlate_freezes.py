"""Correlate CTR freezes with STM/ACQ system_resource gaps for the two
sessions with LSL-startup timeouts on 2026-04-29 (3220 and 3223).

If ACQ shows coincident gaps, that points at shared infrastructure
rather than a CTR-isolated freeze.
"""
import pandas as pd
from _db import get_conn

DATE = "2026-04-29"
SESSIONS = {
    3220: "101031_2026-04-29",
    3223: "101120_2026-04-29",
}


def main():
    conn, tunnel = get_conn()
    try:
        # 1. Pull all LSL-startup wait events for the two affected sessions
        # so we know the timeout timestamps precisely
        all_lsl = []
        for sid, sname in SESSIONS.items():
            df = pd.read_sql_query("""
                SELECT %s::int AS log_session_id, server_time, message
                FROM log_application
                WHERE session_id = %s
                  AND message LIKE 'Waiting for LSL startup took:%%'
                ORDER BY server_time
            """, conn, params=(sid, sname))
            df["sec"] = df["message"].str.extract(r"took: ([\d.]+)").astype(float)
            all_lsl.append(df)
        lsl = pd.concat(all_lsl, ignore_index=True)
        timeouts = lsl[lsl["sec"] > 20].copy()
        # The "took" line is logged AT the END of the wait. So the wait window is
        # [server_time - sec, server_time].
        timeouts["wait_start"] = timeouts["server_time"] - pd.to_timedelta(timeouts["sec"], unit="s")
        timeouts["wait_end"]   = timeouts["server_time"]
        print("=== LSL-startup timeouts (>20s) in 3220 & 3223 ===")
        print(timeouts[["log_session_id", "wait_start", "wait_end", "sec"]].to_string(index=False))

        # 2. For each machine, pull all log_system_resource samples on 2026-04-29
        # within the relevant time range, compute gaps, and find anomalous ones
        machines = ["CTR", "STM", "ACQ_0"]
        gap_summary = {}
        for m in machines:
            df = pd.read_sql_query("""
                SELECT created_at FROM log_system_resource
                WHERE machine_name = %s AND created_at::date = %s::date
                ORDER BY created_at
            """, conn, params=(m, DATE))
            if df.empty:
                print(f"\n--- {m}: no samples on {DATE} ---")
                continue
            df["gap_s"] = df["created_at"].diff().dt.total_seconds()
            gap_summary[m] = df
            big = df[df["gap_s"] > 30]
            print(f"\n--- {m}: {len(df)} samples on {DATE}, "
                  f"first {df['created_at'].min()}, last {df['created_at'].max()}; "
                  f"{len(big)} gap(s) > 30s ---")
            with pd.option_context("display.max_colwidth", 50, "display.width", 200):
                # Show gaps > 30s
                if not big.empty:
                    big_disp = big[["created_at", "gap_s"]].copy()
                    big_disp["gap_min"] = (big_disp["gap_s"] / 60).round(1)
                    big_disp["resumes_at"] = big_disp["created_at"]
                    big_disp["went_silent_at"] = big_disp["created_at"] - pd.to_timedelta(big_disp["gap_s"], unit="s")
                    print(big_disp[["went_silent_at", "resumes_at", "gap_s", "gap_min"]].to_string(index=False))

        # 3. For each timeout, check whether each machine's logger had a coincident gap
        print("\n\n=== Per-timeout cross-machine check ===")
        rows = []
        for _, r in timeouts.iterrows():
            row = {"session": int(r["log_session_id"]),
                   "wait_start": r["wait_start"], "wait_end": r["wait_end"],
                   "lsl_sec": round(r["sec"], 2)}
            for m, df in gap_summary.items():
                # Did this machine have any sample within the wait window?
                in_window = df[(df["created_at"] >= r["wait_start"])
                               & (df["created_at"] <= r["wait_end"])]
                row[f"{m}_samples_in_window"] = len(in_window)
                # If no samples, what's the gap covering this window?
                if in_window.empty:
                    last_before = df[df["created_at"] < r["wait_start"]]
                    next_after  = df[df["created_at"] > r["wait_end"]]
                    if not last_before.empty and not next_after.empty:
                        cover = (next_after["created_at"].iloc[0]
                                 - last_before["created_at"].iloc[-1]).total_seconds()
                        row[f"{m}_covering_gap_s"] = round(cover, 1)
                    else:
                        row[f"{m}_covering_gap_s"] = None
                else:
                    row[f"{m}_covering_gap_s"] = None
            rows.append(row)
        out = pd.DataFrame(rows)
        with pd.option_context("display.max_colwidth", 50, "display.width", 240,
                               "display.max_rows", 50):
            print(out.to_string(index=False))
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()


if __name__ == "__main__":
    main()
