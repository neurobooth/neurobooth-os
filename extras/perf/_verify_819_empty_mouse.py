"""Cross-session verification for #819: does the empty-Mouse hypothesis
predict the user-reported failure list for all affected Wang sessions on
2026-06-02 / 2026-06-03?

Hypothesis under test:
    split_xdf.log_to_database raises IndexError on any task whose Mouse
    stream has zero samples, rolling back the transaction and leaving
    zero log_sensor_file rows for that task.

Prediction:
    For every affected session, the set of tasks with Mouse=0 should
    EXACTLY MATCH the set of tasks reported as missing rows in the
    nightly dataflow warnings.

If the prediction holds across all sessions, #819 is the sole cause.
Any mismatch flags either an incomplete failure list (false positive
in prediction) or a SECOND distinct bug (false negative in prediction).

Run on a machine with Z:\\data mounted. Uses pyxdf.select_streams to
fetch only the Mouse stream from each XDF, so the scan is fast.

Usage:
    python _verify_819_empty_mouse.py                       # default dates
    python _verify_819_empty_mouse.py --dates 2026-06-02   # one date
    python _verify_819_empty_mouse.py --dates 2026-06-02 2026-06-03

The script discovers session directories under Z:\\data whose names
contain any of the given dates. Z:\\data holds every session ever, so
DATE FILTERING IS REQUIRED — otherwise the script scans thousands of
unrelated sessions. The defaults match the user-reported window.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import pyxdf

DATA_ROOT = Path(r"Z:\data")

# Default date range — the window the user reported failures in.
DEFAULT_DATES = ("2026-06-02", "2026-06-03")

# session_id -> list of task-ID substrings the user pasted as failing.
# Substring matching is intentional so colloquial labels ("break 3") line up
# with full task IDs ("break_video_obs_3"). Spurious matches will show up
# as visible "predicted pass, reported FAIL" or vice-versa rows in the table.
FAILURES = {
    "100691_2026-06-02": ["calibration", "break_video_obs_1"],
    "100788_2026-06-02": ["calibration", "break_video_obs_1"],
    "100831_2026-06-02": [
        "calibration", "break_video_obs_1",
        "passage", "pic_desc",
        "break_video_obs_3", "finger_nose", "altern_hand",
    ],
    "101001_2026-06-02": ["calibration", "break_video_obs_1"],
    "100284_2026-06-03": [
        "calibration", "break_video_obs_1", "break_video_obs_2",
        "passage", "pic_desc", "break_video_obs_3",
    ],
    "100789_2026-06-03": [
        "calibration", "break_video_obs_1",
        "passage", "pic_desc", "break_video_obs_3",
    ],
    "101089_2026-06-03": [
        "calibration", "break_video_obs_1", "passage", "pic_desc",
    ],
    "101138_2026-06-03": ["calibration"],
}


def mouse_sample_count(xdf_path: Path) -> Tuple[int, str]:
    """Return (n_samples_in_Mouse, status). status is 'ok' or an error string."""
    try:
        streams, _ = pyxdf.load_xdf(
            str(xdf_path),
            select_streams=[{"name": "Mouse"}],
            verbose=False,
        )
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"
    if not streams:
        return -1, "no Mouse stream in file"
    return len(streams[0]["time_stamps"]), "ok"


def extract_task_id(filename: str) -> str:
    """Pull the task ID from <session>_<date>_<HHh-MMm-SSs>_<task>_R001.xdf."""
    stem = filename
    if stem.endswith(".xdf"):
        stem = stem[:-4]
    if "_R" in stem:
        stem = stem.rsplit("_R", 1)[0]
    parts = stem.split("_")
    for i, p in enumerate(parts):
        if p.endswith("s") and "h-" in p and "m-" in p:
            return "_".join(parts[i + 1:])
    return stem


def task_in_reported_failures(task: str, failures: List[str]) -> bool:
    return any(f in task for f in failures)


def verify_session(session: str, reported_failures: List[str]) -> dict:
    sdir = DATA_ROOT / session
    if not sdir.is_dir():
        print(f"\n=== {session} ===\n  SKIPPED: directory not found at {sdir}")
        return {"ok": False, "skipped": True}

    xdfs = sorted(sdir.glob("*.xdf"))
    print(f"\n=== {session} ({len(xdfs)} XDFs) ===")
    print(f"reported-fail substrings: {reported_failures}")
    print(f"{'task':<34s} {'Mouse_n':>10s}  {'predict':<8s} {'reported':<9s} verdict")
    print("-" * 78)

    mismatches: List[tuple] = []
    n_pred_fail = 0
    n_rep_fail = 0

    for x in xdfs:
        task = extract_task_id(x.name)
        n, status = mouse_sample_count(x)
        if status != "ok":
            print(f"{task:<34s} {'?':>10s}  {'?':<8s} {'?':<9s} LOAD-ERROR: {status}")
            continue

        predicted_fail = (n == 0)
        reported_fail = task_in_reported_failures(task, reported_failures)
        if predicted_fail:
            n_pred_fail += 1
        if reported_fail:
            n_rep_fail += 1
        ok = (predicted_fail == reported_fail)
        verdict = "OK" if ok else "MISMATCH"
        if not ok:
            mismatches.append((task, n, predicted_fail, reported_fail))

        pred_label = "FAIL" if predicted_fail else "pass"
        rep_label = "FAIL" if reported_fail else "pass"
        print(f"{task:<34s} {n:>10d}  {pred_label:<8s} {rep_label:<9s} {verdict}")

    print(f"  -> predicted_fail={n_pred_fail}, reported_fail={n_rep_fail}, "
          f"mismatches={len(mismatches)}")
    return {"ok": len(mismatches) == 0, "mismatches": mismatches,
            "n_pred_fail": n_pred_fail, "n_rep_fail": n_rep_fail}


def discover_sessions(dates: List[str]) -> List[str]:
    """Enumerate session directories under Z:\\data whose names contain any
    of the given date strings. Sorted; duplicates removed."""
    if not DATA_ROOT.is_dir():
        print(f"FATAL: {DATA_ROOT} not accessible", file=sys.stderr)
        sys.exit(2)
    found = []
    for child in DATA_ROOT.iterdir():
        if not child.is_dir():
            continue
        if any(d in child.name for d in dates):
            found.append(child.name)
    return sorted(set(found))


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=list(DEFAULT_DATES),
        help=f"Session-folder date substrings to scan "
             f"(default: {' '.join(DEFAULT_DATES)})",
    )
    args = parser.parse_args()
    dates: List[str] = args.dates

    print(f"verifying #819 empty-Mouse hypothesis under {DATA_ROOT}")
    print(f"date filter: {dates}")

    discovered = discover_sessions(dates)
    print(f"discovered {len(discovered)} session directories matching filter")

    sessions_in_failures = set(FAILURES.keys())
    sessions_discovered = set(discovered)
    only_in_failures = sessions_in_failures - sessions_discovered
    only_discovered = sessions_discovered - sessions_in_failures
    if only_in_failures:
        print(f"WARN: {len(only_in_failures)} session(s) in FAILURES but not "
              f"found on disk: {sorted(only_in_failures)}")
    if only_discovered:
        print(f"NOTE: {len(only_discovered)} session(s) on dates "
              f"{dates} that are NOT in the reported failure list "
              f"(predictions will be checked against an empty failure list):")
        for s in sorted(only_discovered):
            print(f"      {s}")

    sessions_to_check = sorted(sessions_in_failures | sessions_discovered)

    results: Dict[str, dict] = {}
    for session in sessions_to_check:
        failures = FAILURES.get(session, [])
        results[session] = verify_session(session, failures)

    print("\n" + "=" * 78)
    print("OVERALL SUMMARY")
    print("=" * 78)

    all_ok = True
    for session, r in results.items():
        if r.get("skipped"):
            print(f"  {session}: SKIPPED (no directory)")
            continue
        if r["ok"]:
            print(f"  {session}: OK  "
                  f"(predicted_fail={r['n_pred_fail']}, reported_fail={r['n_rep_fail']})")
        else:
            all_ok = False
            print(f"  {session}: MISMATCH "
                  f"(predicted_fail={r['n_pred_fail']}, reported_fail={r['n_rep_fail']})")
            for task, n, pred, rep in r["mismatches"]:
                p_str = "FAIL" if pred else "pass"
                r_str = "FAIL" if rep else "pass"
                print(f"      {task:<34s} Mouse={n}  predicted={p_str}  reported={r_str}")

    print()
    if all_ok:
        print("RESULT: #819 hypothesis CONFIRMED across all sessions.")
        print("Every reported failure has Mouse=0; every other task has Mouse>0.")
        return 0
    print("RESULT: #819 hypothesis NOT FULLY CONFIRMED — see mismatches above.")
    print("Each mismatch is one of:")
    print("  * predicted FAIL, reported pass: a task with empty Mouse is NOT in")
    print("    your warning list. Possible: warning list was incomplete, or that")
    print("    task succeeded via a path that bypassed the bug.")
    print("  * predicted pass, reported FAIL: a task with non-empty Mouse DID fail.")
    print("    Possible: a second, independent bug. Investigate that task separately.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
