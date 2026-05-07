"""Investigate the 31.6s LSL-startup pattern in session 3223."""
import pandas as pd
from _db import get_conn

SESSION_NAME = "101120_2026-04-29"  # 3223 = subject 101120

def main():
    conn, tunnel = get_conn()
    try:
        # 1. Confirm session_id
        sn_q = "SELECT log_session_id, subject_id, date::text AS date FROM log_session WHERE log_session_id = 3223"
        print(pd.read_sql_query(sn_q, conn).to_string(index=False))

        # 2. All Waiting-for-LSL-startup lines for this session, in order
        q1 = """
        SELECT server_time, message
        FROM log_application
        WHERE session_id = %s
          AND message LIKE 'Waiting for LSL startup took:%%'
        ORDER BY server_time
        """
        df = pd.read_sql_query(q1, conn, params=(SESSION_NAME,))
        df["sec"] = df["message"].str.extract(r"took: ([\d.]+)").astype(float)
        print(f"\n=== {len(df)} LSL-startup waits in session 3223 ===")
        print(f"Distribution of seconds:")
        print(df["sec"].describe().round(2).to_string())
        print("\nAll values:")
        print(df.to_string(index=False))

        # 3. Did the timeout warning fire? Check for 'LsLRecording not received' AND
        # other CTR-related issues during the session
        q2 = """
        SELECT server_time, server_type, log_level, function, message
        FROM log_application
        WHERE session_id = %s
          AND (message ILIKE '%%LsLRecording%%not received%%'
            OR message ILIKE '%%lsl%%'
            OR (log_level IN ('WARNING','ERROR','CRITICAL') AND server_type = 'presentation'))
        ORDER BY server_time
        """
        df2 = pd.read_sql_query(q2, conn, params=(SESSION_NAME,))
        df2["message"] = df2["message"].str[:140]
        print(f"\n=== LSL-related + warning lines for session 3223 ({len(df2)}) ===")
        with pd.option_context("display.max_colwidth", 150, "display.width", 240,
                               "display.max_rows", 200):
            print(df2.to_string(index=False))

        # 4. Compare against another session that day to see if it's session-specific
        for sid in ["101031_2026-04-29", "101119_2026-04-29",
                    "100975_2026-04-29", "101123_2026-04-29"]:  # 3220, 3221, 3222, 3224
            d = pd.read_sql_query(q1, conn, params=(sid,))
            d["sec"] = d["message"].str.extract(r"took: ([\d.]+)").astype(float)
            print(f"\n--- {sid}: n={len(d)}, median={d['sec'].median():.2f}, "
                  f"max={d['sec'].max():.2f}, n_over_20s={int((d['sec']>20).sum())}")
    finally:
        conn.close()
        if tunnel is not None:
            tunnel.stop()


if __name__ == "__main__":
    main()
