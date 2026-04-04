"""Is ACQ slow because of 3 mbients or because the machine is busy?

Compare per-device connect times (ACQ vs STM) and look at sequencing
to determine whether the overhead is per-device or machine-level.
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


def ps(series, indent=6):
    pad = " " * indent
    if len(series) == 0:
        print(f"{pad}No data")
        return
    print(f"{pad}Mean: {series.mean():.1f}s  Median: {series.median():.1f}s"
          f"  p75: {series.quantile(0.75):.1f}s"
          f"  Max: {series.max():.1f}s  N={len(series)}")


def main():
    conn, tunnel = get_conn()

    # =================================================================
    # Per-device initial connect: first Attempting -> Setup Completed
    # =================================================================
    q = """
    WITH attempts AS (
        SELECT session_id, server_id,
               SUBSTRING(message FROM 9 FOR 2) AS mbient_id,
               MIN(server_time) AS first_attempt,
               MIN(server_time)::date AS dt
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = '<lambda>'
          AND message LIKE '%%Attempting connection%%'
        GROUP BY session_id, server_id, SUBSTRING(message FROM 9 FOR 2)
    ),
    setups AS (
        SELECT session_id, server_id,
               SUBSTRING(message FROM 9 FOR 2) AS mbient_id,
               MIN(server_time) AS first_setup
        FROM log_application
        WHERE filename = 'mbient.py'
          AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = 'setup'
          AND message LIKE '%%Setup Completed%%'
        GROUP BY session_id, server_id, SUBSTRING(message FROM 9 FOR 2)
    )
    SELECT a.session_id, a.server_id, a.mbient_id, a.dt,
           EXTRACT(EPOCH FROM (s.first_setup - a.first_attempt)) AS device_sec,
           a.first_attempt, s.first_setup
    FROM attempts a
    JOIN setups s ON a.session_id = s.session_id
                 AND a.server_id = s.server_id
                 AND a.mbient_id = s.mbient_id
    WHERE s.first_setup > a.first_attempt
    """
    df = pd.read_sql_query(q, conn)
    df = df[(df["device_sec"] > 0) & (df["device_sec"] < 300)]
    df["first_attempt"] = pd.to_datetime(df["first_attempt"], utc=True)
    df["first_setup"] = pd.to_datetime(df["first_setup"], utc=True)

    print("=" * 75)
    print("1. PER-DEVICE CONNECT TIME (first Attempting -> Setup Completed)")
    print("   If ACQ devices are individually slower, it's machine load.")
    print("   If similar to STM, it's just 3 vs 2 devices.")
    print("=" * 75)

    for mid in ["RH", "LH", "BK", "RF", "LF"]:
        g = df[df["mbient_id"] == mid]
        if g.empty:
            continue
        machine = g["server_id"].iloc[0]
        print(f"\n  {mid} on {machine}:", end="")
        ps(g["device_sec"], indent=1)

    # Compare aggregated: ACQ per-device vs STM per-device
    acq_devs = df[df["server_id"] == "acq"]["device_sec"]
    stm_devs = df[df["server_id"] == "stm"]["device_sec"]
    print(f"\n  --- Aggregate per-device ---")
    print(f"  ACQ (any device):", end="")
    ps(acq_devs, indent=1)
    print(f"  STM (any device):", end="")
    ps(stm_devs, indent=1)
    print(f"\n  Ratio ACQ/STM median: {acq_devs.median() / stm_devs.median():.1f}x")

    # =================================================================
    # 2. SEQUENCING — are ACQ devices connecting in parallel or serial?
    # =================================================================
    print("\n")
    print("=" * 75)
    print("2. SEQUENCING — How much overlap between ACQ devices?")
    print("   Compare sum-of-individual vs wall-clock total")
    print("=" * 75)

    # Per-session: sum of device times vs wall-clock (first attempt to last setup)
    acq_sessions = df[df["server_id"] == "acq"].copy()
    sum_per_session = acq_sessions.groupby("session_id")["device_sec"].sum().rename("sum_devices")
    wall_per_session = acq_sessions.groupby("session_id").apply(
        lambda g: (g["first_setup"].max() - g["first_attempt"].min()).total_seconds()
    ).rename("wall_clock")
    compare = pd.concat([sum_per_session, wall_per_session], axis=1).dropna()
    compare = compare[(compare["wall_clock"] > 0) & (compare["wall_clock"] < 300)]
    compare["overlap_pct"] = (1 - compare["wall_clock"] / compare["sum_devices"]) * 100

    print(f"\n  ACQ machine per session (N={len(compare)}):")
    print(f"    Sum of 3 device times:  Mean={compare['sum_devices'].mean():.1f}s"
          f"  Med={compare['sum_devices'].median():.1f}s")
    print(f"    Wall-clock total:       Mean={compare['wall_clock'].mean():.1f}s"
          f"  Med={compare['wall_clock'].median():.1f}s")
    print(f"    Overlap:                Mean={compare['overlap_pct'].mean():.0f}%"
          f"  Med={compare['overlap_pct'].median():.0f}%")
    print(f"    (0% = fully serial, 67% = fully parallel for 3 devices)")

    # Same for STM
    stm_sessions = df[df["server_id"] == "stm"].copy()
    if len(stm_sessions) > 0:
        sum_stm = stm_sessions.groupby("session_id")["device_sec"].sum().rename("sum_devices")
        wall_stm = stm_sessions.groupby("session_id").apply(
            lambda g: (g["first_setup"].max() - g["first_attempt"].min()).total_seconds()
        ).rename("wall_clock")
        comp_stm = pd.concat([sum_stm, wall_stm], axis=1).dropna()
        comp_stm = comp_stm[(comp_stm["wall_clock"] > 0) & (comp_stm["wall_clock"] < 300)]
        comp_stm["overlap_pct"] = (1 - comp_stm["wall_clock"] / comp_stm["sum_devices"]) * 100

        print(f"\n  STM machine per session (N={len(comp_stm)}):")
        print(f"    Sum of 2 device times:  Mean={comp_stm['sum_devices'].mean():.1f}s"
              f"  Med={comp_stm['sum_devices'].median():.1f}s")
        print(f"    Wall-clock total:       Mean={comp_stm['wall_clock'].mean():.1f}s"
              f"  Med={comp_stm['wall_clock'].median():.1f}s")
        print(f"    Overlap:                Mean={comp_stm['overlap_pct'].mean():.0f}%"
              f"  Med={comp_stm['overlap_pct'].median():.0f}%")
        print(f"    (0% = fully serial, 50% = fully parallel for 2 devices)")

    # =================================================================
    # 3. BLE SCAN DURATION — does ACQ scan take longer?
    # =================================================================
    q_scan = """
    SELECT session_id, server_id, server_time::date AS dt,
           server_time AS scan_time, message
    FROM log_application
    WHERE filename = 'mbient.py'
      AND session_id IS NOT NULL
      AND server_time >= '2025-09-20'
      AND function = 'prepare_scan'
      AND (message LIKE '%%Performing BLE Scan%%' OR message LIKE '%%BLE scan found%%')
    ORDER BY session_id, server_id, server_time
    """
    df_scan = pd.read_sql_query(q_scan, conn)
    df_scan["scan_time"] = pd.to_datetime(df_scan["scan_time"], utc=True)

    # Pair: "Performing BLE Scan" -> "BLE scan found" per session/server
    starts = df_scan[df_scan["message"].str.contains("Performing BLE Scan")]
    ends = df_scan[df_scan["message"].str.contains("BLE scan found")]

    scan_results = []
    for (sid, srv), grp_s in starts.groupby(["session_id", "server_id"]):
        grp_e = ends[(ends["session_id"] == sid) & (ends["server_id"] == srv)]
        if grp_s.empty or grp_e.empty:
            continue
        t0 = grp_s["scan_time"].min()
        t1 = grp_e["scan_time"].min()
        dur = (t1 - t0).total_seconds()
        if 0 < dur < 60:
            scan_results.append({"session_id": sid, "server_id": srv, "scan_sec": dur})

    df_sc = pd.DataFrame(scan_results)

    print("\n")
    print("=" * 75)
    print("3. BLE SCAN DURATION (Performing BLE Scan -> BLE scan found)")
    print("=" * 75)
    for srv in ["acq", "stm"]:
        g = df_sc[df_sc["server_id"] == srv]
        if g.empty:
            continue
        print(f"\n  {srv}:", end="")
        ps(g["scan_sec"], indent=1)

    # =================================================================
    # 4. TIME FROM BLE SCAN TO FIRST ATTEMPT — how long before mbients
    #    start connecting (setup overhead before BLE work begins)
    # =================================================================
    q_scan_to_attempt = """
    WITH scans AS (
        SELECT session_id, server_id, MIN(server_time) AS scan_time
        FROM log_application
        WHERE filename = 'mbient.py' AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = 'prepare_scan' AND message LIKE '%%Performing BLE Scan%%'
        GROUP BY session_id, server_id
    ),
    first_attempts AS (
        SELECT session_id, server_id, MIN(server_time) AS attempt_time
        FROM log_application
        WHERE filename = 'mbient.py' AND session_id IS NOT NULL
          AND server_time >= '2025-09-20'
          AND function = '<lambda>' AND message LIKE '%%Attempting connection%%'
        GROUP BY session_id, server_id
    )
    SELECT s.session_id, s.server_id,
           EXTRACT(EPOCH FROM (fa.attempt_time - s.scan_time)) AS scan_to_attempt_sec
    FROM scans s
    JOIN first_attempts fa ON s.session_id = fa.session_id AND s.server_id = fa.server_id
    """
    df_sta = pd.read_sql_query(q_scan_to_attempt, conn)
    df_sta = df_sta[(df_sta["scan_to_attempt_sec"] > 0) & (df_sta["scan_to_attempt_sec"] < 60)]

    print("\n")
    print("=" * 75)
    print("4. SCAN OVERHEAD (BLE Scan -> first Attempting connection)")
    print("=" * 75)
    for srv in ["acq", "stm"]:
        g = df_sta[df_sta["server_id"] == srv]
        if g.empty:
            continue
        print(f"\n  {srv}:", end="")
        ps(g["scan_to_attempt_sec"], indent=1)

    # =================================================================
    # 5. FIRST vs LAST device on ACQ — is the last device penalized?
    # =================================================================
    print("\n")
    print("=" * 75)
    print("5. ACQ DEVICE ORDER — Is the last device to connect penalized?")
    print("   Per-device connect time by finish order within each session")
    print("=" * 75)

    acq = df[df["server_id"] == "acq"].copy()
    acq["rank"] = acq.groupby("session_id")["first_setup"].rank()
    for rank_val in [1.0, 2.0, 3.0]:
        g = acq[acq["rank"] == rank_val]
        if g.empty:
            continue
        # Which device finishes in this position most often?
        most_common = g["mbient_id"].value_counts().head(3)
        devs = ", ".join(f"{d}={c}" for d, c in most_common.items())
        print(f"\n  #{int(rank_val)} to finish ({devs}):", end="")
        ps(g["device_sec"], indent=1)

    conn.close()
    tunnel.stop()


if __name__ == "__main__":
    main()
