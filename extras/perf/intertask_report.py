"""Inter-task time reporting for Neurobooth MVP-30 sessions.

Computes inter-task gaps using log_sensor_file data, taking the max gap
across all devices for each canonical transition (the "long pole" device).

Key concepts:
  - "Canonical transition": a pair of consecutive tasks in the MVP-30
    collection order (e.g., position 5->6 = fixation -> gaze_holding).
  - "Long pole": for each transition, the device with the largest gap
    determines the overall inter-task time (since all devices must finish
    before the next task starts).
  - "Adjustment": devices that skip tasks (e.g., Intels don't record
    during progress_bar) have their gaps adjusted using the Mic baseline
    to isolate the device overhead from the hidden task durations.

Adjustment strategy:
  When a device sees task A then task C (skipping B), or A then D
  (skipping B and C):
    1. Compute the device's raw gap: A_end to C_start (or D_start)
    2. Compute the Mic's total time for the same span
    3. Device overhead = raw_gap - mic_span
    4. Attribute this to the A->B transition: mic_A_to_B + overhead
  If more than 2 tasks are skipped, the gap is discarded (too much
  uncertainty in the adjustment).

Outlier handling:
  Gaps exceeding MAX_GAP_SECONDS (default 180s / 3 minutes) are
  discarded per-device before computing the long pole. This filters
  breaks (physician visits, bathroom) and stale records from interrupted
  sessions, while retaining legitimately slow system transitions.

Usage:
    # Session summary (Q1)
    python extras/intertask_report.py --session 3140

    # Date range summary with stats (Q3) and per-transition detail (Q4)
    python extras/intertask_report.py --from 2026-03-01 --to 2026-03-23

    # Date range with trend plots (Q2)
    python extras/intertask_report.py --from 2026-03-01 --to 2026-03-23 --plot

    # Direct SSH tunnel connection (from a dev machine)
    python extras/intertask_report.py --direct --from 2026-03-01 --to 2026-03-23

    # Custom gap threshold
    python extras/intertask_report.py --direct --from 2026-03-01 --to 2026-03-23 --max-gap 240
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psycopg2
from sshtunnel import SSHTunnelForwarder

# ---------------------------------------------------------------------------
# MVP-30 canonical task order (Wang environment)
# Source: configs/shared/collections/mvp_030.yml
# ---------------------------------------------------------------------------

MVP30_TASKS = [
    "intro_sess_obs_1",
    "progress_bar_obs_1",
    "intro_occulo_obs_1",
    "calibration_obs_1",
    "pursuit_obs",
    "fixation_no_target_obs_1",
    "gaze_holding_obs_1",
    "saccades_horizontal_obs_1",
    "saccades_vertical_obs_1",
    "break_video_obs_1",
    "progress_bar_obs_2",
    "intro_cog_obs_1",
    "MOT_obs_1",
    "DSC_obs",
    "hevelius_obs",
    "break_video_obs_2",
    "progress_bar_obs_3",
    "intro_speech_obs_1",
    "passage_obs_1",
    "picture_description_obs_1",
    "ahh_obs_1",
    "break_video_obs_3",
    "coord_pause_obs_1",
    "finger_nose_obs_1",
    "foot_tapping_obs_1",
    "altern_hand_mov_obs_1",
    "coord_pause_obs_2",
    "sit_to_stand_obs",
]

# Reverse lookup: task_id -> canonical position index
TASK_INDEX = {t: i for i, t in enumerate(MVP30_TASKS)}

# Max hidden tasks a device can span before we discard the gap.
# At 1 or 2 skipped tasks, we adjust using the Mic baseline.
# At >2, the adjustment is too uncertain and the gap is ignored.
MAX_SKIPPED = 2

# Max plausible inter-task gap in seconds. Anything above this is
# considered a break or stale data, not a system/device delay.
# Based on analysis: Eyelink p97=250s, p98=325s; 180s captures
# legitimate system delays while excluding human breaks.
MAX_GAP_SECONDS = 180

# The Mic records during every task and serves as the universal baseline
# for adjustment calculations.
MIC_DEVICE = "Mic_Yeti_dev_1"

# Devices to exclude from the long-pole calculation. Mouse is excluded
# because it only records during ~7 tasks, making its adjusted gaps
# unreliable (the sparse recording creates large artificial overhead
# values that don't reflect real device startup time).
EXCLUDED_DEVICES = {"Mouse"}

# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------

_DIRECT_SSH = {
    "ssh_host": "neurodoor.nmr.mgh.harvard.edu",
    "ssh_username": "sp1022",
    "ssh_pkey": str(Path.home() / ".ssh" / "id_rsa - sp1022"),
    "remote_db_host": "192.168.100.1",
    "remote_db_port": 5432,
    "local_bind_port": 0,  # OS assigns a unique port
    "db_name": "neurobooth",
    "db_user": "neuroboother",
    "db_password": "neuroboothrocks",
}

_tunnel = None


def get_connection_direct():
    """Connect via SSH tunnel to the production database."""
    global _tunnel
    _tunnel = SSHTunnelForwarder(
        _DIRECT_SSH["ssh_host"],
        ssh_username=_DIRECT_SSH["ssh_username"],
        ssh_pkey=_DIRECT_SSH["ssh_pkey"],
        remote_bind_address=(_DIRECT_SSH["remote_db_host"], _DIRECT_SSH["remote_db_port"]),
        local_bind_address=("localhost", _DIRECT_SSH["local_bind_port"]),
    )
    _tunnel.start()
    return psycopg2.connect(
        database=_DIRECT_SSH["db_name"],
        user=_DIRECT_SSH["db_user"],
        password=_DIRECT_SSH["db_password"],
        host="localhost",
        port=_tunnel.local_bind_port,
    )


def get_connection_config(database=None):
    """Connect using the neurobooth_os config (for use on neurobooth machines)."""
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    import neurobooth_os.config as cfg
    cfg.load_neurobooth_config()
    from neurobooth_os.iout.metadator import get_database_connection
    return get_database_connection(database)


def cleanup():
    """Stop the SSH tunnel if one was opened."""
    global _tunnel
    if _tunnel is not None:
        _tunnel.stop()
        _tunnel = None


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_session_data(conn, session_id: Optional[int] = None,
                       date_from: Optional[str] = None,
                       date_to: Optional[str] = None) -> pd.DataFrame:
    """Fetch per-device, per-task start/end times from log_sensor_file.

    Each row represents one device's recording of one task, with the
    earliest file_start_time and latest file_end_time across all sensors
    for that device/task combination.

    Filters to study1/mvp_030 collection with subject_id > 100001
    (excludes test subjects).
    """
    conditions = [
        "ls.study_id = 'study1'",
        "ls.collection_id = 'mvp_030'",
        "lt.subject_id > '100001'",
        "lsf.file_start_time IS NOT NULL",
    ]
    params = []

    if session_id is not None:
        conditions.append("lt.log_session_id = %s")
        params.append(session_id)
    if date_from is not None:
        conditions.append("ls.date >= %s")
        params.append(date_from)
    if date_to is not None:
        conditions.append("ls.date <= %s")
        params.append(date_to)

    where = " AND ".join(conditions)
    query = f"""
    SELECT
        lsf.device_id,
        lt.log_session_id,
        ls.date AS session_date,
        lt.task_id,
        MIN(lsf.file_start_time) AS task_start,
        MAX(lsf.file_end_time) AS task_end
    FROM log_sensor_file lsf
    JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
    JOIN log_session ls ON lt.log_session_id = ls.log_session_id
    WHERE {where}
    GROUP BY lsf.device_id, lt.log_session_id, ls.date, lt.task_id, lt.log_task_id
    ORDER BY lt.log_session_id, lsf.device_id, MIN(lsf.file_start_time)
    """
    return pd.read_sql_query(query, conn, params=params)


# ---------------------------------------------------------------------------
# Gap computation with adjustment
# ---------------------------------------------------------------------------

def compute_transition_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-transition, per-session inter-task gaps.

    For each canonical transition (position i -> i+1 in MVP30_TASKS),
    computes the "long pole" gap: the max gap across all devices that
    can contribute to that transition.

    A device contributes to a transition if:
      - It sees both tasks directly (0 skipped): raw gap is used.
      - It spans 1-2 skipped tasks and this is the first transition
        in the span: an adjusted gap is computed (see below).
      - The computed gap is <= MAX_GAP_SECONDS.

    Adjustment for skipped tasks:
      When device X sees task A (pos i) then task C or D (pos i+2 or i+3),
      the raw gap includes hidden tasks. To isolate the device overhead:
        1. mic_a_to_b = Mic's gap from A_end to B_start (the first
           hidden task's start)
        2. mic_full_span = Mic's total time from A_end to C_start (or D_start)
        3. overhead = raw_gap - mic_full_span (device's extra time)
        4. adjusted = mic_a_to_b + overhead
      This attributes the overhead to the A->B transition, since the
      device's shutdown from task A is where the delay occurs.

    Sessions without Mic data are skipped (no baseline for adjustment).

    Returns a DataFrame with columns:
        session_id, session_date, from_pos, from_task, to_task, max_gap,
        long_pole_device, mic_gap, n_contributing_devices
    """
    results = []

    for session_id, sess_df in df.groupby("log_session_id"):
        session_date = sess_df["session_date"].iloc[0]

        # Build per-device timelines: list of (task_id, canonical pos,
        # start time, end time), sorted by canonical position.
        device_timelines = {}
        for device, dev_df in sess_df.groupby("device_id"):
            timeline = []
            for _, row in dev_df.iterrows():
                if row["task_id"] in TASK_INDEX:
                    timeline.append({
                        "task_id": row["task_id"],
                        "pos": TASK_INDEX[row["task_id"]],
                        "start": row["task_start"],
                        "end": row["task_end"],
                    })
            timeline.sort(key=lambda x: x["pos"])
            if timeline:
                device_timelines[device] = timeline

        # Skip sessions where the Mic didn't record (can't adjust)
        if MIC_DEVICE not in device_timelines:
            continue

        # Mic lookup: canonical position -> (start_time, end_time)
        mic_lookup = {t["pos"]: (t["start"], t["end"])
                      for t in device_timelines[MIC_DEVICE]}

        # Iterate over each canonical transition
        for canon_pos in range(len(MVP30_TASKS) - 1):
            from_task = MVP30_TASKS[canon_pos]
            to_task = MVP30_TASKS[canon_pos + 1]

            # Mic's direct gap for this transition (for reference)
            mic_gap = None
            if canon_pos in mic_lookup and (canon_pos + 1) in mic_lookup:
                mic_gap = (mic_lookup[canon_pos + 1][0]
                           - mic_lookup[canon_pos][1]).total_seconds()

            # Collect each device's contribution to this transition
            device_gaps = {}

            for device, timeline in device_timelines.items():
                if device in EXCLUDED_DEVICES:
                    continue
                for i in range(len(timeline) - 1):
                    t_from = timeline[i]
                    t_to = timeline[i + 1]

                    n_skipped = t_to["pos"] - t_from["pos"] - 1

                    # Does this device's span cover our canonical transition?
                    if t_from["pos"] <= canon_pos and t_to["pos"] >= canon_pos + 1:
                        raw_gap = (t_to["start"] - t_from["end"]).total_seconds()

                        if raw_gap < 0:
                            continue  # Clock skew or data error

                        if n_skipped == 0:
                            # Device sees both tasks directly
                            if raw_gap <= MAX_GAP_SECONDS:
                                device_gaps[device] = raw_gap

                        elif n_skipped <= MAX_SKIPPED:
                            # Device spans hidden tasks. Only contribute to
                            # the A->B transition (first in the span), since
                            # the device overhead is from shutting down task A.
                            if canon_pos == t_from["pos"]:
                                next_pos = t_from["pos"] + 1
                                if (next_pos in mic_lookup
                                        and t_from["pos"] in mic_lookup
                                        and t_to["pos"] in mic_lookup):
                                    # Mic's A->B gap (what the transition
                                    # would be with no device overhead)
                                    mic_a_to_b = (
                                        mic_lookup[next_pos][0]
                                        - mic_lookup[t_from["pos"]][1]
                                    ).total_seconds()
                                    # Mic's full A->C/D span
                                    mic_full = (
                                        mic_lookup[t_to["pos"]][0]
                                        - mic_lookup[t_from["pos"]][1]
                                    ).total_seconds()
                                    if mic_full > 0:
                                        overhead = raw_gap - mic_full
                                        adjusted = mic_a_to_b + overhead
                                        if 0 <= adjusted <= MAX_GAP_SECONDS:
                                            device_gaps[device] = adjusted
                        # n_skipped > MAX_SKIPPED: too uncertain, skip

                        break  # First span covering this transition wins

            # Record the long pole for this transition
            if device_gaps:
                long_pole = max(device_gaps, key=device_gaps.get)
                results.append({
                    "session_id": session_id,
                    "session_date": session_date,
                    "from_pos": canon_pos,
                    "from_task": from_task,
                    "to_task": to_task,
                    "max_gap": device_gaps[long_pole],
                    "long_pole_device": long_pole,
                    "mic_gap": mic_gap,
                    "n_contributing_devices": len(device_gaps),
                })

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report_session(gaps: pd.DataFrame, session_id: int) -> None:
    """Q1: What is our time between tasks on average for a given session?"""
    sess = gaps[gaps["session_id"] == session_id]
    if sess.empty:
        print(f"No data for session {session_id}")
        return

    print(f"\n=== Session {session_id} ({sess['session_date'].iloc[0]}) ===")
    print(f"Transitions: {len(sess)}")
    print(f"Mean inter-task time: {sess['max_gap'].mean():.1f}s")
    print(f"Median: {sess['max_gap'].median():.1f}s")
    print(f"Std: {sess['max_gap'].std():.1f}s")
    print(f"Min: {sess['max_gap'].min():.1f}s  Max: {sess['max_gap'].max():.1f}s")

    print(f"\nPer-transition breakdown:")
    print(f"{'Pos':>3s}  {'From Task':30s} -> {'To Task':30s}  "
          f"{'Gap':>6s}  {'Long Pole':>20s}  {'Mic':>6s}")
    print("-" * 105)
    for _, row in sess.sort_values("from_pos").iterrows():
        mic_str = f"{row['mic_gap']:.1f}" if row['mic_gap'] is not None else "n/a"
        print(f"{int(row['from_pos']):3d}  {row['from_task']:30s} -> "
              f"{row['to_task']:30s}  {row['max_gap']:6.1f}  "
              f"{row['long_pole_device']:>20s}  {mic_str:>6s}")


def report_date_range(gaps: pd.DataFrame) -> None:
    """Q3: For a given date range, summary statistics for inter-task time."""
    print(f"\n=== Date Range Summary ===")
    print(f"Sessions: {gaps['session_id'].nunique()}")
    print(f"Date range: {gaps['session_date'].min()} to {gaps['session_date'].max()}")
    print(f"Total transitions: {len(gaps)}")

    print(f"\nOverall inter-task time (max gap / long pole):")
    print(f"  Mean:   {gaps['max_gap'].mean():.1f}s")
    print(f"  Median: {gaps['max_gap'].median():.1f}s")
    print(f"  Std:    {gaps['max_gap'].std():.1f}s")
    print(f"  Min:    {gaps['max_gap'].min():.1f}s")
    print(f"  Max:    {gaps['max_gap'].max():.1f}s")

    # Q4 part: per-session summary
    sess_stats = gaps.groupby(["session_id", "session_date"])["max_gap"].agg(
        mean="mean", median="median", std="std", min="min", max="max",
    ).reset_index().sort_values("session_date")

    print(f"\n{'Session':>8s}  {'Date':>12s}  {'Mean':>6s}  {'Med':>6s}  "
          f"{'Std':>6s}  {'Min':>6s}  {'Max':>6s}")
    print("-" * 62)
    for _, row in sess_stats.iterrows():
        print(f"{int(row['session_id']):8d}  {str(row['session_date']):>12s}"
              f"  {row['mean']:6.1f}  {row['median']:6.1f}  {row['std']:6.1f}"
              f"  {row['min']:6.1f}  {row['max']:6.1f}")


def report_per_transition(gaps: pd.DataFrame) -> None:
    """Q4: Per-transition statistics across all sessions in the date range."""
    print(f"\n=== Per-Transition Summary ===")
    trans_stats = gaps.groupby(["from_pos", "from_task", "to_task"])["max_gap"].agg(
        n="count", mean="mean", median="median", std="std", min="min", max="max",
    ).reset_index().sort_values("from_pos")

    print(f"{'Pos':>3s}  {'Transition':55s}  {'N':>4s}  {'Mean':>6s}  "
          f"{'Med':>6s}  {'Std':>6s}  {'Min':>6s}  {'Max':>6s}")
    print("-" * 100)
    for _, row in trans_stats.iterrows():
        transition = f"{row['from_task'][:25]:25s} -> {row['to_task'][:27]:27s}"
        print(f"{int(row['from_pos']):3d}  {transition}  {int(row['n']):4d}"
              f"  {row['mean']:6.1f}  {row['median']:6.1f}  {row['std']:6.1f}"
              f"  {row['min']:6.1f}  {row['max']:6.1f}")


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_by_session(gaps: pd.DataFrame, save_dir: Optional[Path] = None) -> None:
    """Q2: Plot inter-task time trends by session and by date."""
    sess_stats = gaps.groupby(["session_id", "session_date"])["max_gap"].agg(
        mean="mean", median="median",
    ).reset_index().sort_values("session_date")

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

    # Top: by session (chronological order)
    ax1.plot(range(len(sess_stats)), sess_stats["median"],
             'bo-', markersize=5, label="Median")
    ax1.plot(range(len(sess_stats)), sess_stats["mean"],
             'rs-', markersize=4, alpha=0.7, label="Mean")
    ax1.set_xlabel("Session (chronological)")
    ax1.set_ylabel("Inter-task time (seconds)")
    ax1.set_title("Inter-task time by session")
    ax1.legend()
    ax1.grid(axis="y", alpha=0.3)

    # Bottom: by date (daily aggregation)
    day_stats = sess_stats.groupby("session_date").agg(
        day_median=("median", "median"),
        day_mean=("mean", "mean"),
        n_sessions=("session_id", "count"),
    ).reset_index()

    ax2.plot(day_stats["session_date"], day_stats["day_median"],
             'bo-', label="Daily median")
    ax2.plot(day_stats["session_date"], day_stats["day_mean"],
             'rs-', markersize=4, alpha=0.6, label="Daily mean")
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Inter-task time (seconds)")
    ax2.set_title("Inter-task time by date")
    ax2.legend()
    ax2.grid(alpha=0.3)
    fig.autofmt_xdate()

    fig.tight_layout()
    if save_dir:
        path = save_dir / "intertask_by_session.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Saved: {path}")
    else:
        plt.show()


def plot_per_transition(gaps: pd.DataFrame,
                        save_dir: Optional[Path] = None) -> None:
    """Box plot of inter-task time distribution per canonical transition."""
    positions = sorted(gaps["from_pos"].unique())
    labels = [f"{MVP30_TASKS[p][:20]}" for p in positions]
    data = [gaps.loc[gaps["from_pos"] == p, "max_gap"].values for p in positions]

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.boxplot(data, labels=labels, patch_artist=True,
               boxprops=dict(facecolor="lightblue", alpha=0.7),
               medianprops=dict(color="red", linewidth=2))
    ax.set_xlabel("Transition (from task)")
    ax.set_ylabel("Inter-task time (seconds)")
    ax.set_title("Inter-task time distribution per transition")
    plt.xticks(rotation=45, ha="right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()

    if save_dir:
        path = save_dir / "intertask_per_transition.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Saved: {path}")
    else:
        plt.show()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Inter-task time reporting for MVP-30 sessions.")
    parser.add_argument("--session", type=int, default=None,
                        help="Report on a specific session ID (Q1)")
    parser.add_argument("--from", dest="date_from", default=None,
                        help="Start date (YYYY-MM-DD) for date range queries")
    parser.add_argument("--to", dest="date_to", default=None,
                        help="End date (YYYY-MM-DD) for date range queries")
    parser.add_argument("--direct", action="store_true",
                        help="Use SSH tunnel connection (for dev machines)")
    parser.add_argument("--database", default=None,
                        help="Database name override (for neurobooth config)")
    parser.add_argument("--plot", action="store_true",
                        help="Generate trend and distribution plots (Q2)")
    parser.add_argument("--max-gap", type=int, default=180,
                        help="Max plausible gap in seconds (default: 180)")
    parser.add_argument("--save-dir", default=None,
                        help="Directory to save plots (default: show)")
    args = parser.parse_args()

    global MAX_GAP_SECONDS
    MAX_GAP_SECONDS = args.max_gap

    # Connect
    if args.direct:
        conn = get_connection_direct()
    else:
        conn = get_connection_config(args.database)

    # Fetch data
    df = fetch_session_data(conn, session_id=args.session,
                            date_from=args.date_from, date_to=args.date_to)
    conn.close()
    cleanup()

    print(f"Fetched {len(df)} device-task rows across "
          f"{df['log_session_id'].nunique()} sessions.")

    if df.empty:
        print("No data found.")
        return

    # Compute transition gaps
    gaps = compute_transition_gaps(df)
    if gaps.empty:
        print("No valid transition gaps computed.")
        return

    print(f"Computed {len(gaps)} transition gaps.")

    # Reports
    if args.session is not None:
        report_session(gaps, args.session)
    else:
        report_date_range(gaps)
        report_per_transition(gaps)

    # Plots
    if args.plot:
        save_dir = Path(args.save_dir) if args.save_dir else None
        if save_dir:
            save_dir.mkdir(parents=True, exist_ok=True)
        if args.session is None:
            plot_by_session(gaps, save_dir)
            plot_per_transition(gaps, save_dir)
        else:
            print("Plots require a date range (--from / --to), "
                  "not a single session.")


if __name__ == "__main__":
    main()
