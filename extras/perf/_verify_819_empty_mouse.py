"""Cross-session verification for #819: does an empty-stream-anywhere
hypothesis predict the user-reported failure list?

Hypothesis under test:
    split_xdf.log_to_database raises IndexError on any task whose XDF
    contains at least one stream with zero samples, rolling back the
    transaction and leaving zero log_sensor_file rows for that task.

    (The original Mouse-only formulation was a special case: Mouse is
    the most common empty stream because subjects often don't move the
    mouse. But the code path -- `timestamps[0]` in the per-device loop --
    fires on any empty stream that is in the task's device config.)

Prediction:
    For every session in the reported window, the set of tasks with ANY
    empty stream should match the reported failure list, after allowing
    for the per-task device-config filter in split_xdf.parse_xdf (which
    drops streams not configured for the task -- those don't reach
    log_to_database and can't trigger the bug regardless of emptiness).

Mismatch interpretation:
    * predicted FAIL, reported pass: a stream is empty in the XDF but
      isn't in the task's configured device list, so parse_xdf filters
      it out before log_to_database. The script can't see the device
      config, so it over-predicts FAIL. Cross-check by reading the
      empty-stream column the script prints.
    * predicted pass, reported FAIL: no streams empty in the XDF, but
      the task still failed registration. Points to a cause other than
      #819 for that specific task.

Run on a machine with Z:\\data mounted. Loads all streams from each XDF
(slower than the original Mouse-only scan -- expect ~tens of minutes
for May+June together, vs minutes for Mouse-only).

Usage:
    python _verify_819_empty_mouse.py                       # default dates
    python _verify_819_empty_mouse.py --dates 2026-06-02   # one date
    python _verify_819_empty_mouse.py --dates 2026-06-02 2026-06-03

The script discovers session directories under Z:\\data whose names
contain any of the given dates. Z:\\data holds every session ever, so
DATE FILTERING IS REQUIRED -- otherwise the script scans thousands of
unrelated sessions. The defaults match the originally reported window.
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


def empty_streams_in_xdf(xdf_path: Path) -> Tuple[List[str], str]:
    """Return (sorted_list_of_empty_stream_names, status).

    Loads every stream and reports any whose ``time_stamps`` has length 0.
    The bug being verified (#819) fires on ANY empty stream that survives
    parse_xdf's device-config filter, not just Mouse.
    """
    try:
        streams, _ = pyxdf.load_xdf(
            str(xdf_path),
            verbose=False,
            dejitter_timestamps=False,  # skip an unneeded post-processing pass
        )
    except Exception as e:
        return [], f"{type(e).__name__}: {e}"
    empty: List[str] = []
    for s in streams:
        info = s["info"]
        raw_name = info.get("name", ["?"])
        name = raw_name[0] if isinstance(raw_name, list) and raw_name else "?"
        if len(s["time_stamps"]) == 0:
            empty.append(name)
    return sorted(empty), "ok"


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
    print(f"{'task':<34s} {'predict':<8s} {'reported':<9s} {'verdict':<10s} empty_streams")
    print("-" * 90)

    mismatches: List[tuple] = []
    n_pred_fail = 0
    n_rep_fail = 0

    for x in xdfs:
        task = extract_task_id(x.name)
        empty, status = empty_streams_in_xdf(x)
        if status != "ok":
            print(f"{task:<34s} {'?':<8s} {'?':<9s} {'LOAD-ERROR':<10s} {status}")
            continue

        predicted_fail = bool(empty)
        reported_fail = task_in_reported_failures(task, reported_failures)
        if predicted_fail:
            n_pred_fail += 1
        if reported_fail:
            n_rep_fail += 1
        ok = (predicted_fail == reported_fail)
        verdict = "OK" if ok else "MISMATCH"
        if not ok:
            mismatches.append((task, empty, predicted_fail, reported_fail))

        pred_label = "FAIL" if predicted_fail else "pass"
        rep_label = "FAIL" if reported_fail else "pass"
        empty_label = ",".join(empty) if empty else "(none)"
        print(f"{task:<34s} {pred_label:<8s} {rep_label:<9s} {verdict:<10s} {empty_label}")

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

    print(f"verifying #819 empty-stream hypothesis under {DATA_ROOT}")
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
            for task, empty, pred, rep in r["mismatches"]:
                p_str = "FAIL" if pred else "pass"
                r_str = "FAIL" if rep else "pass"
                empty_label = ",".join(empty) if empty else "(none)"
                print(f"      {task:<34s} empty=[{empty_label}]  "
                      f"predicted={p_str}  reported={r_str}")

    print()
    if all_ok:
        print("RESULT: #819 hypothesis CONFIRMED across all sessions.")
        print("Every reported failure has at least one empty stream; every other")
        print("task has no empty streams.")
        return 0
    print("RESULT: #819 hypothesis NOT FULLY CONFIRMED -- see mismatches above.")
    print("Each mismatch is one of:")
    print("  * predicted FAIL, reported pass: at least one stream is empty in the")
    print("    XDF but that stream isn't in the task's device config, so")
    print("    parse_xdf filters it out before log_to_database. The script can't")
    print("    see the device config; cross-check by reading the empty_streams")
    print("    column. If the empty stream(s) aren't ones the task uses, this is")
    print("    a script over-prediction, not a real second bug.")
    print("  * predicted pass, reported FAIL: no streams are empty in the XDF but")
    print("    the task still failed. Points to a cause other than #819 for that")
    print("    specific task. Investigate separately.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
