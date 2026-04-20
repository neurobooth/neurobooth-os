"""Validate that every raw file in a finished session has a matching
log_sensor_file row — without copying anything or modifying the database.

This mirrors the "log_sensor_file_id not found" check inside
``neurobooth_terra.dataflow.copy_files`` (used by neurobooth-terra's
``scripts/dataflow_copy.py``), lifted out so it can be run ad-hoc from a
neurobooth-os checkout right after a session ends, to catch registration
gaps before the end-of-day copy runs.

Preconditions:
    Run XDF post-processing first (``neurobooth_os/iout/split_xdf.py``).
    Without it, log_sensor_file won't have HDF5 paths or timing populated,
    and every .hdf5 on disk will report as "not found". XDF split is
    idempotent — it is safe to run it early here and let the normal EOD
    pipeline run it again:

    * ``split_xdf.write_device_hdf5`` calls ``h5io.write_hdf5(..., overwrite=True)``
    * ``split_xdf.log_to_database`` is UPDATE-then-INSERT guarded by
      ``NOT (sensor_file_path @> ARRAY[<hdf5>])``, so a second run is a
      no-op for rows already populated.

DB connection:
    Uses the same SSH tunnel + credentials as the other perf scripts, via
    ``_db.get_conn()`` → ``extras/perf/db_credentials.json``.

Usage:
    python validate_session_files.py --nas-dir /path/to/NAS
    python validate_session_files.py --nas-dir /path/to/NAS 100001_2026-04-19
    python validate_session_files.py --nas-dir /path/to/NAS 100001_2026-04-19 100002_2026-04-19

Exit codes: 0 if every trackable file is registered, 1 if any are missing.
"""
import argparse
import os
import sys

from _db import get_conn


# Mirror the exclusion list in neurobooth_terra.dataflow.copy_files:
# these extensions are not tracked in log_sensor_file.
UNTRACKED_EXTENSIONS = ("xdf", "txt", "csv", "jittered", "asc", "log")


def list_session_files(session_dir: str) -> list:
    """Walk a session directory and return every file in the form stored
    in log_sensor_file.sensor_file_path: ``<session>/<basename>``.
    """
    session_name = os.path.basename(os.path.normpath(session_dir))
    files = []
    for root, _, basenames in os.walk(session_dir):
        for b in basenames:
            rel = os.path.relpath(os.path.join(root, b), session_dir)
            rel = rel.replace(os.sep, "/")
            files.append(f"{session_name}/{rel}")
    return files


_VALIDATE_SQL = """
SELECT 1
FROM log_sensor_file lsf
JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
WHERE lsf.sensor_file_path @> ARRAY[%s]::text[]
  AND lt.task_id IS NOT NULL
LIMIT 1
"""


def validate_session(conn, session: str, src_dir: str) -> tuple:
    """Validate one session. Returns ``(n_total, n_found, n_missing)``."""
    session_dir = os.path.join(src_dir, session)
    if not os.path.isdir(session_dir):
        print(f"[{session}] skipped — directory not found at {session_dir}")
        return 0, 0, 0

    all_files = list_session_files(session_dir)
    trackable = [f for f in all_files
                 if not any(ext in f for ext in UNTRACKED_EXTENSIONS)]
    n_skipped = len(all_files) - len(trackable)

    missing = []
    with conn.cursor() as cur:
        for fname in trackable:
            cur.execute(_VALIDATE_SQL, (fname,))
            if cur.fetchone() is None:
                missing.append(fname)

    n_total = len(trackable)
    n_found = n_total - len(missing)
    print(f"[{session}] {n_total} trackable files, "
          f"{n_found} registered, {len(missing)} missing "
          f"({n_skipped} untracked-extension files skipped)")
    for f in missing:
        print(f"  log_sensor_file_id not found for {f}")
    return n_total, n_found, len(missing)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--nas-dir", required=True,
                        help="Path to the NAS root containing session folders.")
    parser.add_argument("sessions", nargs="*",
                        help="Session names (e.g. 100001_2026-04-19). "
                             "If omitted, every folder under --nas-dir is checked "
                             "(except 'old').")
    args = parser.parse_args()

    if not os.path.isdir(args.nas_dir):
        parser.error(f"--nas-dir does not exist: {args.nas_dir}")

    if args.sessions:
        sessions = args.sessions
    else:
        sessions = [d for d in os.listdir(args.nas_dir)
                    if os.path.isdir(os.path.join(args.nas_dir, d))
                    and d != "old"]

    total = found = missing = 0
    conn, tunnel = get_conn()
    try:
        for session in sessions:
            t, f, m = validate_session(conn, session, args.nas_dir)
            total += t
            found += f
            missing += m
    finally:
        conn.close()
        tunnel.stop()

    print("=" * 60)
    print(f"Sessions checked:      {len(sessions)}")
    print(f"Total trackable files: {total}")
    print(f"Registered:            {found}")
    print(f"Missing:               {missing}")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
