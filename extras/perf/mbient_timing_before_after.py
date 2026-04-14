"""Mbient timing before/after ACQ_1 cutover (March 4, 2026).

Before: RF/LF managed by STM presentation service
After:  RF/LF managed by ACQ_1 acquisition service on STM machine

Broken out by machine (server_id: stm vs acq) so the two acquisition
services are never conflated.
"""

import pandas as pd

from _db import get_conn

CUTOVER = "2026-03-04"


def ps(series, indent=6):
    pad = " " * indent
    if len(series) == 0:
        print(f"{pad}No data")
        return
    print(f"{pad}Mean: {series.mean():.1f}s  Median: {series.median():.1f}s"
          f"  p75: {series.quantile(0.75):.1f}s"
          f"  Min: {series.min():.1f}s  Max: {series.max():.1f}s  N={len(series)}")


def main():
    conn, tunnel = get_conn()

    # =================================================================
    # 1. CONNECT DEVICES — BLE Scan -> last Starting Streaming
    # =================================================================
    q_connect = """
    WITH events AS (
        SELECT session_id, server_id,
               server_time, function, message,
               SUBSTRING(message FROM 9 FOR 2) AS mbient_id,
               server_time::date AS dt
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND (
            (function = 'prepare_scan' AND message LIKE '%%Performing BLE Scan%%')
            OR (function = 'start' AND message LIKE '%%Starting Streaming%%')
          )
    ),
    first_scan AS (
        SELECT session_id, server_id,
               MIN(server_time) AS scan_time,
               MIN(dt) AS dt
        FROM events WHERE function = 'prepare_scan'
        GROUP BY session_id, server_id
    ),
    connect_end AS (
        SELECT e.session_id, e.server_id, fs.dt,
               fs.scan_time,
               MAX(e.server_time) AS last_stream
        FROM events e
        JOIN first_scan fs ON e.session_id = fs.session_id
                          AND e.server_id = fs.server_id
        WHERE e.function = 'start'
          AND e.server_time > fs.scan_time
          AND e.server_time <= fs.scan_time + INTERVAL '5 minutes'
        GROUP BY e.session_id, e.server_id, fs.dt, fs.scan_time
    )
    SELECT session_id, server_id, dt,
           EXTRACT(EPOCH FROM (last_stream - scan_time)) AS connect_sec
    FROM connect_end
    """
    df_c = pd.read_sql_query(q_connect, conn)
    df_c = df_c[(df_c["connect_sec"] > 0) & (df_c["connect_sec"] < 300)]
    df_c["period"] = df_c["dt"].apply(
        lambda d: "After" if str(d) >= CUTOVER else "Before"
    )

    print("=" * 75)
    print("1. CONNECT DEVICES (BLE Scan -> last Starting Streaming)")
    print(f"   Cutover: {CUTOVER}  (v0.61.0 — RF/LF moved to ACQ_1)")
    print("=" * 75)

    for machine in ["acq", "stm"]:
        m = df_c[df_c["server_id"] == machine]
        if machine == "acq":
            label = "ACQ machine [RH, LH, BK] — ACQ_0"
        else:
            label = "STM machine [RF, LF] — STM (before) / ACQ_1 (after)"
        print(f"\n  {label}")
        for period in ["Before", "After"]:
            g = m[m["period"] == period]
            print(f"    {period:6s}:", end="")
            ps(g["connect_sec"], indent=1)

    total = df_c.groupby(["session_id", "period"])["connect_sec"].max().reset_index()
    print(f"\n  Total (wall-clock = max across machines)")
    for period in ["Before", "After"]:
        g = total[total["period"] == period]
        print(f"    {period:6s}:", end="")
        ps(g["connect_sec"], indent=1)

    # =================================================================
    # 2. MBIENT-RESET PAUSE — per device
    # =================================================================
    q_reset = """
    WITH reset_starts AS (
        SELECT session_id, server_id,
               SUBSTRING(message FROM 9 FOR 2) AS mbient_id,
               server_time, server_time::date AS dt,
               ROW_NUMBER() OVER (
                   PARTITION BY session_id, server_id, SUBSTRING(message FROM 9 FOR 2)
                   ORDER BY server_time
               ) AS rn
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = 'reset_and_reconnect'
          AND message LIKE '%%Resetting'
    ),
    reset_ends AS (
        SELECT session_id, server_id,
               SUBSTRING(message FROM 9 FOR 2) AS mbient_id,
               server_time,
               ROW_NUMBER() OVER (
                   PARTITION BY session_id, server_id, SUBSTRING(message FROM 9 FOR 2)
                   ORDER BY server_time
               ) AS rn
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = 'reset_and_reconnect'
          AND message LIKE '%%Reset Completed%%'
    )
    SELECT s.session_id, s.server_id, s.mbient_id, s.dt,
           EXTRACT(EPOCH FROM (e.server_time - s.server_time)) AS reset_sec
    FROM reset_starts s
    JOIN reset_ends e ON s.session_id = e.session_id
                     AND s.server_id = e.server_id
                     AND s.mbient_id = e.mbient_id
                     AND s.rn = e.rn
    """
    df_r = pd.read_sql_query(q_reset, conn)
    df_r = df_r[(df_r["reset_sec"] > 0) & (df_r["reset_sec"] < 300)]
    df_r["period"] = df_r["dt"].apply(
        lambda d: "After" if str(d) >= CUTOVER else "Before"
    )

    print("\n")
    print("=" * 75)
    print("2. MBIENT-RESET PAUSE (Resetting -> Reset Completed)")
    print(f"   Cutover: {CUTOVER}")
    print("=" * 75)

    # Per device
    print("\n  --- Per device ---")
    for mid in ["RH", "LH", "BK", "RF", "LF"]:
        g = df_r[df_r["mbient_id"] == mid]
        if g.empty:
            continue
        machine = g["server_id"].iloc[0]
        if machine == "acq":
            svc = "ACQ_0"
        else:
            svc = "STM->ACQ_1"
        print(f"\n  {mid} on {machine} ({svc}):")
        for period in ["Before", "After"]:
            p = g[g["period"] == period]
            print(f"    {period:6s}:", end="")
            ps(p["reset_sec"], indent=1)

    # Per machine (max across devices per session reset event)
    machine_reset = (
        df_r.groupby(["session_id", "server_id", "period"])
        .agg(reset_sec=("reset_sec", "max"))
        .reset_index()
    )

    print(f"\n  --- Per machine (max across devices per session) ---")
    for machine in ["acq", "stm"]:
        m = machine_reset[machine_reset["server_id"] == machine]
        if machine == "acq":
            label = "ACQ machine [RH, LH, BK] — ACQ_0"
        else:
            label = "STM machine [RF, LF] — STM->ACQ_1"
        print(f"\n  {label}")
        for period in ["Before", "After"]:
            g = m[m["period"] == period]
            print(f"    {period:6s}:", end="")
            ps(g["reset_sec"], indent=1)

    total_r = machine_reset.groupby(["session_id", "period"])["reset_sec"].max().reset_index()
    print(f"\n  Total (wall-clock = max across machines)")
    for period in ["Before", "After"]:
        g = total_r[total_r["period"] == period]
        print(f"    {period:6s}:", end="")
        ps(g["reset_sec"], indent=1)

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
