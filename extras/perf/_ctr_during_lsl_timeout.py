"""During each LSL-startup-timeout window in session 3223, what was CTR doing?

Look for any CTR-side trace that landed during the 31.6s windows:
- log_application rows with server_type='control' (or whatever CTR uses)
- log_system_resource samples (CTR has its own SystemResourceLogger thread,
  per gui.py:706, writing every 10s — gaps would indicate process-level
  freeze beyond just the main thread)
"""
import pandas as pd
from _db import get_conn

SESSION_NAME = "101120_2026-04-29"  # session 3223

# The 5 timeout windows (each ~31.6s long, starting from when STM's
# _wait_for_lsl_recording_to_start began polling).
# Use server_time of the "Waiting for LSL startup took: 31.62" log entry as
# the END of the window, then 31.6s before for the start.
TIMEOUTS_END = [
    "2026-04-29 19:56:44.713206",
    "2026-04-29 20:01:06.415293",
    "2026-04-29 20:02:41.507213",
    "2026-04-29 20:03:22.463487",
    "2026-04-29 20:04:05.777592",
]


def main():
    conn, tunnel = get_conn()
    try:
        # 0. Confirm CTR writes to log_system_resource at all + show overall sample
        # cadence for the session window
        ranges = pd.read_sql_query("""
            SELECT machine_name, COUNT(*) AS n,
                   MIN(created_at) AS first, MAX(created_at) AS last
            FROM log_system_resource
            WHERE created_at BETWEEN '2026-04-29 19:25' AND '2026-04-29 20:35'
            GROUP BY machine_name ORDER BY machine_name
        """, conn)
        print("=== log_system_resource activity 19:25 - 20:35 UTC ===")
        print(ranges.to_string(index=False))

        # 1. What server_types appear in log_application for this session?
        q1 = """
        SELECT server_type, server_id, COUNT(*) AS n,
               MIN(server_time) AS first_seen, MAX(server_time) AS last_seen
        FROM log_application
        WHERE session_id = %s
        GROUP BY server_type, server_id
        ORDER BY server_type, server_id
        """
        print("=== server_type / server_id breakdown for session 3223 ===")
        print(pd.read_sql_query(q1, conn, params=(SESSION_NAME,)).to_string(index=False))

        # 2. log_system_resource: schema and any CTR rows for the day
        cols = pd.read_sql_query("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'log_system_resource' ORDER BY ordinal_position""", conn)
        print(f"\n=== log_system_resource columns ===")
        print(", ".join(cols["column_name"].tolist()))

        # 3. Per-window: any log_application or log_system_resource rows
        # that landed *during* each timeout window
        for end_ts in TIMEOUTS_END:
            end_t = pd.Timestamp(end_ts, tz="UTC")
            start_t = end_t - pd.Timedelta(seconds=31.6)
            print(f"\n\n--- window {start_t} -> {end_t} ---")

            # log_application — anything from any source during the window
            la = pd.read_sql_query("""
                SELECT server_time, server_type, server_id, log_level, function, message
                FROM log_application
                WHERE server_time BETWEEN %s AND %s
                  AND session_id = %s
                ORDER BY server_time
            """, conn, params=(start_t, end_t, SESSION_NAME))
            la = la[~la["message"].str.contains("MESSAGE RECEIVED", na=False)]
            la["message"] = la["message"].str[:120]
            print(f"  log_application rows during window: {len(la)}")
            n_ctr = (la["server_type"] == "control").sum() if "control" in la["server_type"].unique() else 0
            n_stm = (la["server_type"] == "presentation").sum()
            n_acq = (la["server_type"] == "acquisition").sum()
            print(f"    by server_type: control={n_ctr}  presentation={n_stm}  acquisition={n_acq}")
            # If there are any CTR rows during the window, that's evidence of life
            ctr_rows = la[la["server_type"] == "control"]
            if not ctr_rows.empty:
                print(f"  CTR rows during window:")
                with pd.option_context("display.max_colwidth", 130, "display.width", 240):
                    print(ctr_rows.to_string(index=False))

            # log_system_resource — does CTR have a sample during the window?
            try:
                lsr = pd.read_sql_query("""
                    SELECT * FROM log_system_resource
                    WHERE created_at BETWEEN %s AND %s
                      AND machine_name = 'CTR'
                    ORDER BY created_at
                """, conn, params=(start_t, end_t))
                print(f"  log_system_resource rows for CTR during window: {len(lsr)}")
                if not lsr.empty:
                    keep = [c for c in ["created_at", "machine_name", "cpu_usage",
                                         "ram_used", "ram_total"]
                            if c in lsr.columns]
                    print(lsr[keep].to_string(index=False))
            except Exception as e:
                print(f"  log_system_resource query failed: {e}")
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()


if __name__ == "__main__":
    main()
