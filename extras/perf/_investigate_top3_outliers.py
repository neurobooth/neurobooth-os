"""Find the 3 longest transitions in this week's CSV and pull the
log_application window around each to look for attributable causes.
"""
import pandas as pd
from _db import get_conn

CSV = "intertask_from_applog.csv"
TOP_N = 3
WINDOW_BEFORE = 30  # seconds before the transition started
WINDOW_AFTER  = 5   # seconds after end


def main():
    df = pd.read_csv(CSV)
    df["from_finished_at"] = pd.to_datetime(df["from_finished_at"])
    df["to_started_at"]    = pd.to_datetime(df["to_started_at"])
    df["transition_at"]    = pd.to_datetime(df["transition_at"])

    top = df.nlargest(TOP_N, "transition_sec")[
        ["log_session_id", "from_task", "to_task", "transition_sec",
         "from_finished_at", "to_started_at", "transition_at",
         "stm_stop_acq_sec", "stm_wait_acq_sec", "stm_idle_sec",
         "acq0_stop_sec", "acq0_start_sec", "acq1_stop_sec", "acq1_start_sec"]
    ].reset_index(drop=True)

    print("=== Top 3 longest transitions ===")
    with pd.option_context("display.max_colwidth", 30, "display.width", 220):
        print(top.to_string(index=False))

    conn, tunnel = get_conn()
    try:
        for i, r in top.iterrows():
            print(f"\n\n========= #{i+1}: session {int(r['log_session_id'])} "
                  f"{r['from_task']} -> {r['to_task']}: {r['transition_sec']:.1f}s =========")
            print(f"  STM phases — stop_acq={r['stm_stop_acq_sec']}  "
                  f"wait_acq={r['stm_wait_acq_sec']}  idle={r['stm_idle_sec']}")
            print(f"  ACQ_0 — stop={r['acq0_stop_sec']}  start={r['acq0_start_sec']}")
            print(f"  ACQ_1 — stop={r['acq1_stop_sec']}  start={r['acq1_start_sec']}")
            print(f"  Window: {r['from_finished_at']} -> {r['to_started_at']} -> {r['transition_at']}")

            win_start = r["from_finished_at"] - pd.Timedelta(seconds=WINDOW_BEFORE)
            win_end   = r["transition_at"]    + pd.Timedelta(seconds=WINDOW_AFTER)

            q = """
            SELECT server_time, server_type, server_id, log_level, device, function, message
            FROM log_application
            WHERE server_time BETWEEN %s AND %s
            ORDER BY server_time
            """
            la = pd.read_sql_query(q, conn, params=(win_start, win_end))
            # Drop noisiest debug lines that would bury the signal
            la = la[~la["message"].str.contains("MESSAGE RECEIVED", na=False)]
            # Surface anomalies: warnings/errors, retries, resets, long waits
            anom = la[
                (la["log_level"].isin(["WARNING", "ERROR", "CRITICAL"]))
                | la["message"].str.contains(
                    "retry|reset|reconnect|disconn|timeout|abort|fail|exception|"
                    "wait.*took|stop.*took|start.*took|skip|drop|stale",
                    case=False, na=False, regex=True
                )
            ].copy()
            anom["message"] = anom["message"].str[:160]

            print(f"\n  Anomalies + phase-time lines in window ({len(anom)} of {len(la)}):")
            with pd.option_context("display.max_colwidth", 170, "display.width", 280,
                                   "display.max_rows", 200):
                print(anom[["server_time", "server_type", "server_id", "log_level",
                            "device", "function", "message"]].to_string(index=False))
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()


if __name__ == "__main__":
    main()
