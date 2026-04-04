"""Mbient connection and reset timing analysis from log_application.

Initial connect flow per device:
  BLE Scan -> Attempting connection -> Connected via BLE ->
  Device Model -> Resetting Device -> Disconnected during reset ->
  Attempting connection -> Connected -> Setup Completed -> Starting Streaming

Mid-session reset flow (coord_pause tasks):
  reset_and_reconnect: Resetting -> stop -> reset: Resetting Device ->
  disconnect_callback -> Attempting connection -> Connected ->
  Setup Completed -> Starting Streaming -> reset_and_reconnect: Reset Completed
"""

import psycopg2
import pandas as pd
from sshtunnel import SSHTunnelForwarder
from pathlib import Path


def get_conn():
    tunnel = SSHTunnelForwarder(
        "neurodoor.nmr.mgh.harvard.edu",
        ssh_username="sp1022",
        ssh_pkey=str(Path.home() / ".ssh" / "id_rsa - sp1022"),
        remote_bind_address=("192.168.100.1", 5432),
        local_bind_address=("localhost", 0),  # OS assigns a unique port
    )
    tunnel.start()
    conn = psycopg2.connect(
        database="neurobooth",
        user="neuroboother",
        password="neuroboothrocks",
        host="localhost",
        port=tunnel.local_bind_port,
    )
    return conn, tunnel


def ps(series, indent=4):
    pad = " " * indent
    if len(series) == 0:
        print(f"{pad}No data")
        return
    std_str = f"  Std: {series.std():.1f}s" if len(series) > 1 else ""
    print(f"{pad}Mean: {series.mean():.1f}s  Median: {series.median():.1f}s{std_str}")
    print(f"{pad}p25: {series.quantile(0.25):.1f}s  p75: {series.quantile(0.75):.1f}s"
          f"  Min: {series.min():.1f}s  Max: {series.max():.1f}s  N={len(series)}")


def main():
    conn, tunnel = get_conn()

    # =================================================================
    # 1. CONNECT DEVICES — BLE Scan -> last Starting Streaming
    # =================================================================
    q_connect = """
    WITH events AS (
        SELECT session_id, server_type, server_id, server_time,
               function, message,
               SUBSTRING(message FROM E'\\\\[([A-Z]{2});') AS mbient_id,
               server_time::date AS dt
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND (
            (function = 'prepare_scan' AND message LIKE '%%Performing BLE Scan%%')
            OR (function = 'start' AND message LIKE '%%Starting Streaming%%')
            OR (function = '<lambda>' AND message LIKE '%%Attempting connection%%')
            OR (function = 'setup' AND message LIKE '%%Setup Completed%%')
          )
    ),
    -- Get the first BLE scan per session/server (marks start of initial connect)
    first_scan AS (
        SELECT session_id, server_type, MIN(server_time) AS scan_time
        FROM events WHERE function = 'prepare_scan'
        GROUP BY session_id, server_type
    ),
    -- Get initial connect: last Starting Streaming within 5 min of BLE scan
    connect_end AS (
        SELECT e.session_id, e.server_type, e.server_id,
               fs.scan_time,
               MAX(e.server_time) AS last_stream,
               e.dt
        FROM events e
        JOIN first_scan fs ON e.session_id = fs.session_id AND e.server_type = fs.server_type
        WHERE e.function = 'start'
          AND e.server_time > fs.scan_time
          AND e.server_time <= fs.scan_time + INTERVAL '5 minutes'
        GROUP BY e.session_id, e.server_type, e.server_id, fs.scan_time, e.dt
    )
    SELECT session_id, server_type, server_id, dt,
           EXTRACT(EPOCH FROM (last_stream - scan_time)) AS connect_sec
    FROM connect_end
    """
    df_connect = pd.read_sql_query(q_connect, conn)
    df_connect = df_connect[(df_connect["connect_sec"] > 0) & (df_connect["connect_sec"] < 300)]

    print("=" * 70)
    print("1. CONNECT DEVICES — Mbient connection time")
    print("   (BLE Scan -> last Starting Streaming per server)")
    print("=" * 70)

    total = df_connect.groupby("session_id")["connect_sec"].max()
    print(f"\n  Total (wall-clock = max across servers):")
    ps(total)

    for srv in ["acquisition", "presentation"]:
        g = df_connect[df_connect["server_type"] == srv]
        if g.empty:
            continue
        sid = g["server_id"].iloc[0]
        devices = "RH, LH, BK" if srv == "acquisition" else "RF, LF"
        print(f"\n  {srv} ({sid}) [{devices}]:")
        ps(g["connect_sec"])

    # =================================================================
    # 2. MBIENT-RESET PAUSE — reset_and_reconnect: Resetting -> Reset Completed
    # =================================================================
    q_reset = """
    WITH reset_events AS (
        SELECT session_id, server_type, server_id, server_time,
               message, function,
               SUBSTRING(message FROM E'\\\\[([A-Z]{2});') AS mbient_id,
               server_time::date AS dt
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = 'reset_and_reconnect'
          AND (message LIKE '%%Resetting' OR message LIKE '%%Reset Completed%%')
    ),
    -- Per-device: pair each "Resetting" with the next "Reset Completed"
    reset_starts AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY session_id, server_type, mbient_id ORDER BY server_time) AS rn
        FROM reset_events WHERE message LIKE '%%Resetting'
    ),
    reset_ends AS (
        SELECT *, ROW_NUMBER() OVER (PARTITION BY session_id, server_type, mbient_id ORDER BY server_time) AS rn
        FROM reset_events WHERE message LIKE '%%Reset Completed%%'
    )
    SELECT s.session_id, s.server_type, s.server_id, s.mbient_id, s.dt,
           s.server_time AS reset_start,
           e.server_time AS reset_end,
           EXTRACT(EPOCH FROM (e.server_time - s.server_time)) AS reset_sec
    FROM reset_starts s
    JOIN reset_ends e ON s.session_id = e.session_id
                     AND s.server_type = e.server_type
                     AND s.mbient_id = e.mbient_id
                     AND s.rn = e.rn
    """
    df_reset = pd.read_sql_query(q_reset, conn)
    df_reset = df_reset[(df_reset["reset_sec"] > 0) & (df_reset["reset_sec"] < 300)]

    print("\n")
    print("=" * 70)
    print("2. MBIENT-RESET PAUSE — Per-device reset time")
    print("   (reset_and_reconnect: Resetting -> Reset Completed)")
    print("=" * 70)

    for mid in ["RH", "LH", "BK", "RF", "LF"]:
        g = df_reset[df_reset["mbient_id"] == mid]
        if g.empty:
            continue
        srv = g["server_type"].iloc[0]
        sid = g["server_id"].iloc[0]
        print(f"\n  {mid} on {srv} ({sid}):")
        ps(g["reset_sec"])

    # Total per server (max across devices per reset event)
    # Group by session + approximate time window (10 min bins)
    df_reset["reset_start"] = pd.to_datetime(df_reset["reset_start"], utc=True)
    df_reset["reset_group"] = (
        df_reset.groupby(["session_id", "server_type"])["reset_start"]
        .transform(lambda x: ((x - x.min()).apply(lambda td: td.total_seconds()) // 600).astype(int))
    )
    srv_reset = (df_reset.groupby(["session_id", "server_type", "server_id", "dt", "reset_group"])
                 .agg(reset_sec=("reset_sec", "max"), n_devices=("mbient_id", "nunique"))
                 .reset_index())

    print(f"\n  --- Total per server (max across devices per reset event) ---")
    total_r = srv_reset.groupby(["session_id", "reset_group"])["reset_sec"].max()
    print(f"\n  Total (wall-clock = max across servers):")
    ps(total_r)

    for srv in ["acquisition", "presentation"]:
        g = srv_reset[srv_reset["server_type"] == srv]
        if g.empty:
            continue
        devices = "RH, LH, BK" if srv == "acquisition" else "RF, LF"
        print(f"\n  {srv} [{devices}]:")
        ps(g["reset_sec"])

    # =================================================================
    # 3. TIME-PERIOD BREAKDOWN
    # =================================================================
    periods = [
        ("6-mo baseline (Sep 20 - Mar 20)", "2025-09-20", "2026-03-20"),
        ("Last week (Mar 24-26)", "2026-03-24", "2026-03-26"),
        ("Mon-Tue (Mar 30-31)", "2026-03-30", "2026-03-31"),
        ("Apr 1-2", "2026-04-01", "2026-04-02"),
    ]

    print("\n")
    print("=" * 70)
    print("3. TIME-PERIOD BREAKDOWN")
    print("=" * 70)

    for phase_name, df_phase, label_col in [
        ("Connect Devices (wall-clock per server)", df_connect, "connect_sec"),
        ("Mbient-Reset Pause (per device)", df_reset, "reset_sec"),
    ]:
        print(f"\n  --- {phase_name} ---")
        for label, d0, d1 in periods:
            subset = df_phase[(df_phase["dt"] >= pd.Timestamp(d0).date()) &
                              (df_phase["dt"] <= pd.Timestamp(d1).date())]
            if subset.empty:
                print(f"\n    {label}: no data")
                continue
            print(f"\n    {label}:")
            for srv in ["acquisition", "presentation"]:
                g = subset[subset["server_type"] == srv]
                if g.empty:
                    continue
                devices = "RH,LH,BK" if srv == "acquisition" else "RF,LF"
                print(f"      {srv} [{devices}]: "
                      f"Mean={g[label_col].mean():.1f}s  Med={g[label_col].median():.1f}s  "
                      f"p75={g[label_col].quantile(0.75):.1f}s  N={len(g)}")

    # =================================================================
    # 4. RF/LF MIGRATION CHECK
    # =================================================================
    q_mig = """
    SELECT DISTINCT server_type, server_id, server_time::date AS dt,
           SUBSTRING(message FROM E'\\\\[([A-Z]{2});') AS mbient_id
    FROM log_application
    WHERE filename = 'mbient.py'
      AND session_id IS NOT NULL
      AND server_time >= '2026-03-01'
      AND (message LIKE '%%RF;%%' OR message LIKE '%%LF;%%')
    ORDER BY dt DESC
    LIMIT 30
    """
    df_mig = pd.read_sql_query(q_mig, conn)

    print("\n")
    print("=" * 70)
    print("4. RF/LF SERVER PLACEMENT — STM -> ACQ migration check")
    print("=" * 70)
    acq = df_mig[df_mig["server_type"] == "acquisition"]
    if not acq.empty:
        print("  Found RF/LF on acquisition:")
        print(acq.to_string(index=False))
    else:
        latest = df_mig.groupby(["mbient_id", "server_type"])["dt"].max()
        print("  RF and LF remain on presentation (STM) only.")
        print(f"  Last seen: {latest.to_dict()}")
        print("  No 'after' data — migration has not occurred in the logs yet.")

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
