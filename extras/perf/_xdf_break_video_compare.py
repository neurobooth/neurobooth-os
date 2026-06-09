"""Load break_video_obs_1 (failed) and break_video_obs_2 (clean) from
session 100788_2026-06-02 and compare structure stream-by-stream.

Files were copied from Z:\\data to C:\\Users\\lw412\\Downloads for analysis.
"""
import sys
import traceback
from pathlib import Path

import pyxdf

DOWNLOADS = Path(r"C:\Users\lw412\Downloads")
FILES = {
    "obs_1 (FAILED in postprocess)": DOWNLOADS / "100788_2026-06-02_15h-33m-45s_break_video_obs_1_R001.xdf",
    "obs_2 (clean)":                 DOWNLOADS / "100788_2026-06-02_15h-52m-25s_break_video_obs_2_R001.xdf",
}


def _scalar(field) -> str:
    """LSL xml fields come back as one-element lists."""
    return field[0] if isinstance(field, list) and field else str(field)


def summarize(label: str, path: Path):
    print(f"\n===== {label} =====")
    print(f"path: {path}")
    print(f"size: {path.stat().st_size:,} bytes")
    try:
        streams, header = pyxdf.load_xdf(str(path), verbose=False)
    except Exception as e:
        print(f"\nLOAD FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        return None

    print(f"parsed OK: {len(streams)} streams")
    rows = []
    for s in streams:
        info = s["info"]
        name = _scalar(info.get("name", ["?"]))
        stype = _scalar(info.get("type", ["?"]))
        srate = _scalar(info.get("nominal_srate", ["0"]))
        nchan = _scalar(info.get("channel_count", ["?"]))
        nsamp = len(s["time_stamps"])
        if nsamp:
            t0 = s["time_stamps"][0]
            t1 = s["time_stamps"][-1]
            span = t1 - t0
        else:
            t0 = t1 = span = None
        rows.append({
            "name": name,
            "type": stype,
            "ch": nchan,
            "srate": srate,
            "n": nsamp,
            "t0": t0,
            "t1": t1,
            "span": span,
        })

    rows.sort(key=lambda r: r["name"])
    print(f"\n{'name':<24s} {'type':<10s} {'ch':>3s} {'srate':>7s} {'samples':>10s} {'span_s':>10s}")
    print("-" * 78)
    for r in rows:
        span_s = f"{r['span']:.2f}" if r["span"] is not None else "EMPTY"
        srate = r["srate"]
        print(f"{r['name']:<24s} {r['type']:<10s} {str(r['ch']):>3s} {str(srate):>7s} {r['n']:>10d} {span_s:>10s}")

    return {r["name"]: r for r in rows}


def diff_streams(a: dict, b: dict, a_label: str, b_label: str):
    if a is None or b is None:
        return
    names_a = set(a.keys())
    names_b = set(b.keys())
    only_a = names_a - names_b
    only_b = names_b - names_a
    common = sorted(names_a & names_b)

    print("\n===== STREAM-SET DIFF =====")
    if only_a:
        print(f"only in {a_label}: {sorted(only_a)}")
    if only_b:
        print(f"only in {b_label}: {sorted(only_b)}")
    if not only_a and not only_b:
        print("stream NAMES identical between the two files")

    print(f"\n===== PER-STREAM SAMPLE-COUNT DIFF (common {len(common)} streams) =====")
    print(f"{'name':<24s} {a_label[:20]:>22s} {b_label[:20]:>22s}")
    print("-" * 72)
    for n in common:
        ra = a[n]
        rb = b[n]
        marker_a = "" if ra["n"] > 0 else " <EMPTY>"
        marker_b = "" if rb["n"] > 0 else " <EMPTY>"
        print(f"{n:<24s} {ra['n']:>15d}{marker_a:>7s} {rb['n']:>15d}{marker_b:>7s}")


def main():
    labels = list(FILES.keys())
    summary = {}
    for label, path in FILES.items():
        if not path.exists():
            print(f"MISSING: {path}")
            sys.exit(2)
        summary[label] = summarize(label, path)
    diff_streams(summary[labels[0]], summary[labels[1]], "obs_1", "obs_2")


if __name__ == "__main__":
    main()
