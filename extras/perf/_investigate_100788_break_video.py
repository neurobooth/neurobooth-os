"""One-off: pull log_application for session 100788_2026-06-02 and surface
diagnostic context around the break_video_obs_1 failure (no log_sensor_file
rows produced for any device for that task).

Task started 15:33:45 local per the HDF5 filename:
  100788_2026-06-02_15h-33m-45s_break_video_obs_1_R001-...
"""
import sys
from pathlib import Path

import pandas as pd

from _db import get_conn

SESSION = "100788_2026-06-02"
TASK_TIME = "2026-06-02 15:33:45"  # local; server_time should be the same

SUSPICIOUS_KW = [
    "LabRecorder", "lsl_recording", "subscription", "exited with code",
    "access violation", "3221225477", "0xc0000005", "0xc0000374",
    "taskkill", "segfault", "PANIC", "crashed", "aborted", "finalize",
    "liesl", "start_recording", "stop_recording", "TIMEOUT", "FAILED",
    "split_xdf", "ParseError", "EOF", "truncated",
]


def main() -> int:
    conn, tunnel = get_conn()
    try:
        # 1. Schema sanity check.
        cols = pd.read_sql_query(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'log_application'
            ORDER BY ordinal_position
            """,
            conn,
        )
        print("=== log_application schema ===")
        print(cols.to_string(index=False))
        print()

        # 2. Top-level row counts for this session.
        df = pd.read_sql_query(
            """
            SELECT *
            FROM log_application
            WHERE session_id = %s
            ORDER BY server_time
            """,
            conn,
            params=(SESSION,),
        )
        print(f"=== Session {SESSION} ===")
        print(f"total rows: {len(df)}")
        if len(df) == 0:
            print("(no rows; session_id may not match — try variants)")
            # Try LIKE in case the recorded session_id has a suffix.
            df_like = pd.read_sql_query(
                """
                SELECT DISTINCT session_id
                FROM log_application
                WHERE session_id LIKE %s
                ORDER BY session_id
                """,
                conn,
                params=(SESSION + "%",),
            )
            print("session_ids matching prefix:")
            print(df_like.to_string(index=False))
            return 0

        print("server_type counts:")
        print(df["server_type"].value_counts().to_string())
        print()
        print(f"first row: {df['server_time'].min()}")
        print(f"last row:  {df['server_time'].max()}")
        print()

        # 3. Rows containing any suspicious keyword.
        msg = df["message"].astype(str)
        mask = pd.Series(False, index=df.index)
        for kw in SUSPICIOUS_KW:
            mask |= msg.str.contains(kw, case=False, na=False)

        susp = df[mask].copy()
        print(f"=== Suspicious-keyword rows: {len(susp)} ===")
        for _, row in susp.iterrows():
            t = row["server_time"]
            stype = row["server_type"]
            fn = row.get("function", "")
            m = str(row["message"])[:280].replace("\n", " | ")
            print(f"[{t}] {stype:<14s} {fn:<28s} | {m}")
        print()

        # 4. All non-INFO rows for the session (ERROR / WARNING / etc).
        print("=== log_level value counts ===")
        print(df["log_level"].value_counts().to_string())
        print()
        non_info = df[~df["log_level"].isin(["INFO", "DEBUG"])].copy()
        print(f"=== Non-INFO rows: {len(non_info)} ===")
        for _, row in non_info.iterrows():
            t = row["server_time"]
            lvl = row["log_level"]
            stype = row["server_type"]
            fn = row.get("function", "")
            m = str(row["message"])[:240].replace("\n", " | ")
            print(f"[{t}] {lvl:<8s} {stype:<14s} {fn:<24s} | {m}")
        print()

        # 5. Task boundary events (STARTING TASK / FINISHED TASK).
        task_mask = (
            df["message"].astype(str).str.startswith("STARTING TASK")
            | df["message"].astype(str).str.startswith("FINISHED TASK")
        )
        task_rows = df[task_mask].copy()
        print(f"=== Task boundary events: {len(task_rows)} ===")
        for _, row in task_rows.iterrows():
            t = row["server_time"]
            stype = row["server_type"]
            m = str(row["message"])[:200]
            print(f"[{t}] {stype:<14s} | {m}")
        print()

        # 6. Tight window around break_video_obs_1 (UTC: 19:33:00 - 19:42:00).
        win_start = pd.Timestamp("2026-06-02 19:33:00", tz="UTC")
        win_end = pd.Timestamp("2026-06-02 19:42:00", tz="UTC")
        df_ts = pd.to_datetime(df["server_time"], utc=True)
        win = df[(df_ts >= win_start) & (df_ts <= win_end)].copy()
        print(f"=== Window {win_start} -> {win_end}: {len(win)} rows ===")
        for _, row in win.iterrows():
            t = row["server_time"]
            lvl = row["log_level"]
            stype = row["server_type"]
            fn = row.get("function", "")
            m = str(row["message"])[:240].replace("\n", " | ")
            print(f"[{t}] {lvl:<8s} {stype:<14s} {fn:<24s} | {m}")

        # 7. Save the full session log to CSV for offline inspection.
        out = Path(__file__).parent / f"applog_{SESSION}.csv"
        df.to_csv(out, index=False)
        print(f"\nFull session log saved: {out}")

    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            tunnel.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
