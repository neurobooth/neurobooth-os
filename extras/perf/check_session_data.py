"""Post-session real-device data-collection report.

Opens every per-task XDF in a session folder and reports, per LSL stream,
the channel count, sample count, effective sampling rate and duration, so
you can confirm each real device actually *captured data* — not merely that
files exist. Also checks EyeLink ``.edf`` and iPhone ``.mov`` presence/size,
and (with ``--db``) cross-checks the local database (log_task /
log_sensor_file) for the session.

This complements ``extras/perf/validate_session_files.py``, which checks that
files are *registered* in log_sensor_file (via the production SSH tunnel).
This script instead checks that the streams inside the files contain data,
and it talks to whatever DB the active NB_CONFIG points at (e.g. the local
dod_neurobooth), not the tunnel.

Usage:
    python check_session_data.py                      # latest session under the data root
    python check_session_data.py 100001_2026-07-08    # a named session
    python check_session_data.py --dir C:/path/to/session_folder
    python check_session_data.py 100001_2026-07-08 --db   # also cross-check the local DB

Expected real devices for the dod_laptop config: EyeLink, Audio (mic),
IPhoneFrameIndex (iPhone), Mouse, Marker. Edit EXPECTED below for other envs.

Exit code: 0 if every expected device produced a non-empty stream in at least
one task, else 1.
"""
import argparse
import os
import sys
import glob

import pyxdf

# LSL stream name (substring, case-insensitive) -> friendly device label.
STREAM_DEVICE = {
    "eyelink": "EyeLink",
    "audio": "Mic",
    "iphoneframeindex": "iPhone",
    "iphone": "iPhone",
    "mouse": "Mouse",
    "marker": "Marker",
}
# Devices we expect to see produce data in a dod_laptop real-device session.
EXPECTED = ["EyeLink", "Mic", "Mouse", "Marker"]  # iPhone reported but not required (often dropped)

DEFAULT_DATA_ROOT = r"C:\neurobooth\neurobooth_data"


def device_for(stream_name: str) -> str:
    low = (stream_name or "").lower()
    for key, label in STREAM_DEVICE.items():
        if key in low:
            return label
    return stream_name or "?"


def find_session_dir(session: str, explicit_dir: str, data_root: str) -> str:
    if explicit_dir:
        return explicit_dir
    if session:
        return os.path.join(data_root, session)
    # latest folder under data_root by mtime
    subdirs = [os.path.join(data_root, d) for d in os.listdir(data_root)
               if os.path.isdir(os.path.join(data_root, d)) and d != "old"]
    if not subdirs:
        sys.exit(f"No session folders under {data_root}")
    return max(subdirs, key=os.path.getmtime)


def size_str(path: str) -> str:
    b = os.path.getsize(path)
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.0f}{unit}"
        b /= 1024
    return f"{b:.1f}TB"


def report_xdf(path: str, seen: dict) -> None:
    """Print per-stream stats for one XDF; accumulate max samples per device in `seen`."""
    print(f"\n  {os.path.basename(path)}  ({size_str(path)})")
    try:
        streams, _ = pyxdf.load_xdf(path, dejitter_timestamps=False, synchronize_clocks=False)
    except Exception as e:  # noqa: BLE001 - report and continue
        print(f"    !! failed to load: {e!r}")
        return
    if not streams:
        print("    !! no streams in file")
        return
    for s in sorted(streams, key=lambda x: x["info"]["name"][0].lower()):
        name = s["info"]["name"][0]
        stype = s["info"]["type"][0] if s["info"].get("type") else ""
        nch = int(s["info"]["channel_count"][0])
        ts = s["time_stamps"]
        n = len(ts)
        nominal = float(s["info"]["nominal_srate"][0] or 0)
        if n > 1:
            dur = ts[-1] - ts[0]
            eff = (n - 1) / dur if dur > 0 else 0.0
        else:
            dur = 0.0
            eff = 0.0
        dev = device_for(name)
        if n == 0:
            flag = "   <-- EMPTY"
        elif n <= 1:
            flag = "   <-- INIT-ONLY (no stream data captured)"
        else:
            flag = ""
        print(f"    {dev:8} {name:22} type={stype:10} ch={nch:<3} "
              f"samples={n:<8} eff_rate={eff:7.1f}Hz (nom={nominal:.0f}) dur={dur:6.1f}s{flag}")
        seen[dev] = max(seen.get(dev, 0), n)


def report_native_files(session_dir: str) -> None:
    edfs = sorted(glob.glob(os.path.join(session_dir, "*.edf")))
    movs = sorted(glob.glob(os.path.join(session_dir, "*.mov")))
    print("\n  EyeLink native .edf files:")
    if edfs:
        for f in edfs:
            print(f"    {os.path.basename(f):55} {size_str(f)}")
    else:
        print("    (none) <-- EyeLink produced no .edf")
    print("  iPhone .mov video files:")
    if movs:
        for f in movs:
            print(f"    {os.path.basename(f):55} {size_str(f)}")
    else:
        print("    (none) <-- iPhone produced no video (disconnect/panic or not enabled)")


def db_cross_check(session_name: str) -> None:
    """Optional: count log_task / log_sensor_file rows for the session in the active DB."""
    os.environ.setdefault("NB_CONFIG", os.environ.get("NB_CONFIG", r"C:\Users\lw412\.neurobooth_os"))
    import warnings
    warnings.filterwarnings("ignore")
    from neurobooth_os import config
    config.load_config(validate_paths=False)
    db = config.neurobooth_config.database
    import psycopg2
    conn = psycopg2.connect(host=db.host, port=db.port, user=db.user,
                            password=db.password.get_secret_value(), dbname=db.dbname, connect_timeout=5)
    cur = conn.cursor()
    like = f"%{session_name}%"
    print(f"\n  DB cross-check ({db.dbname}):")
    # Match via sensor_file_path (contains "<session>/<file>"), avoiding schema assumptions.
    cur.execute("SELECT count(*) FROM log_sensor_file WHERE sensor_file_path::text LIKE %s", (like,))
    print(f"    log_sensor_file rows referencing session: {cur.fetchone()[0]}")
    cur.execute("""SELECT DISTINCT lt.task_id
                   FROM log_sensor_file lsf JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
                   WHERE lsf.sensor_file_path::text LIKE %s AND lt.task_id IS NOT NULL
                   ORDER BY lt.task_id""", (like,))
    tasks = [r[0] for r in cur.fetchall()]
    print(f"    tasks with registered files ({len(tasks)}): {tasks}")
    print("    (run split_xdf.py first for HDF5 rows; use validate_session_files.py for full registration audit)")
    cur.close(); conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", nargs="?", help="Session name, e.g. 100001_2026-07-08")
    ap.add_argument("--dir", dest="explicit_dir", help="Explicit path to a session folder")
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT, help=f"Data root (default {DEFAULT_DATA_ROOT})")
    ap.add_argument("--db", action="store_true", help="Also cross-check the active DB (log_task/log_sensor_file)")
    args = ap.parse_args()

    session_dir = find_session_dir(args.session, args.explicit_dir, args.data_root)
    if not os.path.isdir(session_dir):
        sys.exit(f"Session folder not found: {session_dir}")
    session_name = os.path.basename(os.path.normpath(session_dir))

    print("=" * 78)
    print(f"Session data report: {session_name}")
    print(f"Folder: {session_dir}")
    print("=" * 78)

    xdfs = sorted(glob.glob(os.path.join(session_dir, "*.xdf")))
    if not xdfs:
        print("No .xdf files found in this session.")
    seen = {}
    for x in xdfs:
        report_xdf(x, seen)

    report_native_files(session_dir)

    if args.db:
        try:
            db_cross_check(session_name)
        except Exception as e:  # noqa: BLE001
            print(f"\n  DB cross-check failed: {e!r}")

    # Per-device verdict
    # A stream with <=1 sample is init-only (device registered but never streamed).
    MIN_SAMPLES = 2
    print("\n" + "=" * 78)
    print("Per-device verdict (max samples across tasks):")
    all_devices = sorted(set(list(seen.keys()) + EXPECTED))
    ok = True
    for dev in all_devices:
        n = seen.get(dev, 0)
        required = dev in EXPECTED
        if n >= MIN_SAMPLES:
            status = "PASS"
        elif required:
            status = "FAIL (no data captured)"; ok = False
        else:
            status = "no capture (not required)"
        print(f"  {dev:8} {status:26} max_samples={n}")
    print("=" * 78)
    print("RESULT:", "PASS - all required devices captured data" if ok
          else "FAIL - a required device captured no data (see above)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
