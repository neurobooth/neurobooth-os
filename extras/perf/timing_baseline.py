"""Emit a booth timing-microbenchmark baseline as one JSON artefact.

Strategy doc (``docs/timing_test_strategy.md``) **Test C**: the per-primitive
accuracy and jitter of the five wait primitives the whole timing stack is
built on, plus an optional PsychoPy flip-interval jitter probe. This is the
most OS-scheduler-sensitive layer and the cheapest signal for the Win10 ->
Win11 regression question (#759 concern #3, issue #761). No lab, no camera,
no devices, no subject -- it runs headless on a booth in seconds.

The output is the shared baseline envelope, identical in shape to
``extras/perf/win11_readiness.py`` (same ``machine`` block, ``verdict``,
``collection_errors``): every measured number is kept; the ``verdict`` is
*derived from* the numbers as a convenience and never replaces them. A single
run cannot say "regressed" -- that is a comparison, done by
``extras/perf/compare_timing.py`` against a locked Win10 baseline. This tool
only *captures*.

Usage::

    uv run python extras/perf/timing_baseline.py [--role CTR|STM|ACQ|spare]
        [--reps N] [--interval SECONDS] [--with-flip-stats]
        [--flip-frames N] [--out PATH] [--stdout]

By default writes ``<log_dir>/timing/<os>/<hostname>.json`` -- ``<log_dir>``
is the neurobooth ``local_log_dir`` from the loaded config (the same place
the crash/startup logs go), falling back to ``NB_INSTALL`` then the user
home. ``<os>`` is ``win10`` / ``win11`` / ``unknown`` from the OS build, so
the Win10 baseline and Win11 pilot land in sibling trees for the comparator.
Runtime artefacts stay out of the repo working tree; a locked baseline is a
deliberate copy into ``extras/perf/baselines/timing/`` (see
``docs/timing_summary.md``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from _baseline_common import (
    CollectionError,
    build_envelope,
    collect_os_identity,
    resolved_log_dir,
)

SCHEMA_VERSION = 1
SCHEMA_NAME = "timing_baseline"

# Win11's first build is 22000; anything below is Win10 for our booths.
WIN11_MIN_BUILD = 22000

# Sanity bounds for the single-run verdict. These are NOT pass/fail
# thresholds for the OS question -- that is compare_timing.py's job against a
# real Win10 baseline. They only flag a run that is obviously broken (e.g.
# the machine was under heavy load) so it is not silently committed as a
# baseline. A flag means "a human looks", never "fail".
SANITY_MEAN_ERROR_FACTOR = 5.0  # mean abs error > 5x requested interval
SANITY_MAX_ERROR_FACTOR = 50.0  # worst single wait > 50x requested interval


def os_segment(machine: Dict[str, Any]) -> str:
    """Derive the ``win10`` / ``win11`` / ``unknown`` path segment.

    Prefers the OS build number (unambiguous: Win11 >= 22000); falls back to
    the caption string; returns ``"unknown"`` if neither is conclusive so a
    misfiled artefact is obvious rather than silently mislabeled.

    Args:
        machine: The ``machine`` identity block.

    Returns:
        One of ``"win10"``, ``"win11"``, ``"unknown"``.
    """
    build_raw = machine.get("os_build")
    try:
        build = int(str(build_raw).strip())
    except (TypeError, ValueError):
        build = None
    if build is not None:
        return "win11" if build >= WIN11_MIN_BUILD else "win10"

    caption = (machine.get("os_caption") or "").lower()
    if "windows 11" in caption:
        return "win11"
    if "windows 10" in caption:
        return "win10"
    return "unknown"


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Linear-interpolated percentile (numpy 'linear' method), pure-Python.

    Kept dependency-free so the summary layer is unit-testable without the
    scientific stack and gives bit-stable expected values in tests.

    Args:
        sorted_vals: Ascending-sorted samples (non-empty).
        pct: Percentile in [0, 100].

    Returns:
        The interpolated percentile value.
    """
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    rank = (pct / 100.0) * (len(sorted_vals) - 1)
    low = int(rank)
    high = min(low + 1, len(sorted_vals) - 1)
    frac = rank - low
    return float(sorted_vals[low] * (1.0 - frac) + sorted_vals[high] * frac)


def summarize_errors(
    intervals: Dict[str, List[float]], requested: float
) -> Dict[str, Dict[str, float]]:
    """Reduce realized intervals to per-primitive absolute-error statistics.

    Pure function (no I/O, no global state, no heavy imports) so it is
    directly unit-testable on synthetic data.

    Args:
        intervals: Primitive name -> list of realized wait durations (s).
        requested: The requested wait the primitives were asked for (s).

    Returns:
        Primitive name -> ``{mean, sd, p95, p99, max, n}`` of the absolute
        error ``|realized - requested|`` in seconds.
    """
    summary: Dict[str, Dict[str, float]] = {}
    for name, realized in intervals.items():
        errs = sorted(abs(v - requested) for v in realized)
        n = len(errs)
        if n == 0:
            summary[name] = {
                "mean": 0.0,
                "sd": 0.0,
                "p95": 0.0,
                "p99": 0.0,
                "max": 0.0,
                "n": 0,
            }
            continue
        mean = sum(errs) / n
        var = sum((e - mean) ** 2 for e in errs) / n  # population SD (np.std)
        summary[name] = {
            "mean": mean,
            "sd": var**0.5,
            "p95": _percentile(errs, 95.0),
            "p99": _percentile(errs, 99.0),
            "max": errs[-1],
            "n": n,
        }
    return summary


def run_microbench(
    snap_errors: List[CollectionError],
    interval: float,
    reps: int,
) -> Optional[Dict[str, List[float]]]:
    """Run Test C, importing the canonical loop from ``time_clocks_variance``.

    The measurement lives in exactly one place (``extras/time_clocks_variance
    .measure_primitives``); this only locates and invokes it. ``extras/`` is
    put on ``sys.path`` the same way the other perf scripts cross-tree-import.

    Args:
        snap_errors: Collection-error accumulator; a failure here is fatal to
            the artefact (the microbench is the core signal) and re-raised
            after being recorded.
        interval: Requested wait per repetition (s).
        reps: Repetitions per primitive.

    Returns:
        The raw realized-interval mapping, or ``None`` only if it could not
        run (after recording the error).
    """
    extras_dir = Path(__file__).resolve().parent.parent
    if str(extras_dir) not in sys.path:
        sys.path.insert(0, str(extras_dir))
    try:
        from time_clocks_variance import measure_primitives
    except Exception as exc:  # noqa: BLE001
        snap_errors.append(CollectionError.from_exception("microbench.import", exc))
        return None
    try:
        return measure_primitives(time_period=interval, n_reps=reps)
    except Exception as exc:  # noqa: BLE001
        snap_errors.append(CollectionError.from_exception("microbench.run", exc))
        return None


def collect_flip_stats(
    snap_errors: List[CollectionError],
    n_frames: int,
) -> Optional[Dict[str, Any]]:
    """Best-effort PsychoPy flip-interval jitter probe (display part of G4).

    Opens a PsychoPy window with frame-interval recording on, flips
    ``n_frames`` times, and returns realized flip-interval statistics plus
    the dropped-flip count. This is intentionally a *minimal self-contained*
    flip loop, NOT the full saccades task: the strategy doc demotes the
    camera/bag saccades run to a one-off confirmatory measurement
    (``timing_test_recording_audit.md`` §1.1: the in-repo
    ``Saccade_synch`` entry point also needs a deployed ``timing_test_task_1``
    config that is not in this repo and an EyeLink). The signal the doc wants
    here -- requested-vs-actual flip jitter and dropped flips, no camera -- is
    fully captured by this probe and is far more replicable.

    Entirely optional and best-effort: any failure (no PsychoPy, no display,
    headless CI) is recorded as a non-fatal ``collection_error`` and ``None``
    is returned, so the microbench artefact is still emitted.

    Args:
        snap_errors: Non-fatal collection-error accumulator.
        n_frames: Number of flips to time.

    Returns:
        ``{requested_hz, mean_ms, sd_ms, p95_ms, p99_ms, max_ms,
        dropped_flips, n}`` or ``None`` if the probe could not run.
    """
    win = None
    try:
        from psychopy import visual

        win = visual.Window(
            fullscr=False,
            size=(640, 480),
            color=(0, 0, 0),
            allowGUI=False,
            waitBlanking=True,
        )
        measured_hz = win.getActualFrameRate(nIdentical=10, nMaxFrames=240)
        win.recordFrameIntervals = True
        for i in range(int(n_frames)):
            win.color = (1, 1, 1) if i % 2 else (-1, -1, -1)
            win.flip()
        intervals_ms = [iv * 1000.0 for iv in win.frameIntervals]
        dropped = int(getattr(win, "nDroppedFrames", 0))
    except Exception as exc:  # noqa: BLE001
        snap_errors.append(CollectionError.from_exception("flip_stats", exc))
        return None
    finally:
        if win is not None:
            try:
                win.close()
            except Exception:  # noqa: BLE001
                pass

    if not intervals_ms:
        snap_errors.append(
            CollectionError(
                field="flip_stats",
                message="window opened but no frame intervals were recorded",
            )
        )
        return None

    ordered = sorted(intervals_ms)
    n = len(ordered)
    mean = sum(ordered) / n
    var = sum((v - mean) ** 2 for v in ordered) / n
    return {
        "requested_hz": (round(float(measured_hz), 3) if measured_hz else None),
        "mean_ms": mean,
        "sd_ms": var**0.5,
        "p95_ms": _percentile(ordered, 95.0),
        "p99_ms": _percentile(ordered, 99.0),
        "max_ms": ordered[-1],
        "dropped_flips": dropped,
        "n": n,
    }


def derive_verdict(metrics: Dict[str, Any], interval: float) -> Dict[str, Any]:
    """Derive an honest single-run verdict from the captured numbers.

    A single microbench run cannot answer the #759 question -- that needs an
    A/B against a locked Win10 baseline (``compare_timing.py``). So the
    category is always ``CAPTURED``; ``reasons`` records that, plus any
    primitive whose error is so large the run looks contaminated (machine
    under load) and should probably be re-taken before being committed as a
    baseline. Never pass/fail; flags are for human eyes.

    Args:
        metrics: The assembled ``metrics`` block.
        interval: The requested microbench interval (s), for sanity scaling.

    Returns:
        ``{category, reasons, remediation_hints}``.
    """
    reasons: List[str] = [
        "Single-run capture. Regression assessment is a comparison: run "
        "extras/perf/compare_timing.py against the locked Win10 baseline."
    ]
    hints: List[str] = []

    micro = metrics.get("microbench") or {}
    for name, stats in micro.items():
        if stats.get("n", 0) == 0:
            continue
        if stats["mean"] > SANITY_MEAN_ERROR_FACTOR * interval:
            reasons.append(
                f"microbench '{name}' mean error {stats['mean'] * 1000:.2f} ms "
                f">> requested {interval * 1000:.2f} ms -- run may be "
                f"contaminated by machine load; consider re-taking."
            )
            hints.append("Re-run on an otherwise-idle booth (close GUI, no recording).")
        elif stats["max"] > SANITY_MAX_ERROR_FACTOR * interval:
            reasons.append(
                f"microbench '{name}' worst wait {stats['max'] * 1000:.2f} ms "
                f"is a large outlier vs requested {interval * 1000:.2f} ms."
            )

    category = "CAPTURED_WITH_ERRORS" if metrics.get("_had_errors") else "CAPTURED"
    return {
        "category": category,
        "reasons": reasons,
        "remediation_hints": sorted(set(hints)),
    }


def default_output_path(base: Path, os_seg: str, hostname: str) -> Path:
    """Return ``<base>/<os_seg>/<hostname>.json``.

    Pure (the resolved ``base`` directory is passed in, not discovered here)
    so it stays unit-testable without touching the real log directory.

    Args:
        base: Resolved output root (e.g. ``resolved_log_dir("timing")``).
        os_seg: ``win10`` / ``win11`` / ``unknown``.
        hostname: Machine hostname.
    """
    return Path(base) / os_seg / f"{hostname}.json"


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--role",
        choices=["CTR", "STM", "ACQ", "spare"],
        help="Booth role for this machine; recorded in the JSON for triage.",
    )
    parser.add_argument(
        "--reps",
        type=int,
        default=100,
        help="Microbench repetitions per primitive (default: 100).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.01,
        help="Requested wait per repetition, seconds (default: 0.01).",
    )
    parser.add_argument(
        "--with-flip-stats",
        action="store_true",
        help="Also run the optional PsychoPy flip-interval jitter probe "
        "(needs a display; best-effort, never fatal).",
    )
    parser.add_argument(
        "--flip-frames",
        type=int,
        default=600,
        help="Flips to time when --with-flip-stats is set (default: 600).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output path. Defaults to "
        "<log_dir>/timing/<os>/<hostname>.json (log_dir from the neurobooth "
        "config local_log_dir; NB_INSTALL/home fallback).",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print JSON to stdout in addition to writing the file.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    errors: List[CollectionError] = []

    print("Collecting timing microbenchmark baseline...", file=sys.stderr)

    machine, os_errors = collect_os_identity(args.role)
    errors.extend(os_errors)

    out_base = resolved_log_dir("timing")

    metrics: Dict[str, Any] = {
        "requested_interval_s": args.interval,
        "reps": args.reps,
    }

    intervals = run_microbench(errors, args.interval, args.reps)
    if intervals is None:
        # The microbench is the core signal; without it the artefact is not
        # a usable baseline. Emit it anyway (with the error recorded) so the
        # failure is visible, but exit non-zero.
        metrics["microbench"] = {}
        metrics["_had_errors"] = True
        verdict = derive_verdict(metrics, args.interval)
        metrics.pop("_had_errors", None)
        payload = build_envelope(
            schema_name=SCHEMA_NAME,
            schema_version=SCHEMA_VERSION,
            machine=machine,
            blocks={"metrics": metrics},
            verdict=verdict,
            errors=errors,
        )
        out_path = args.out or default_output_path(
            out_base, os_segment(machine), machine.get("hostname", "unknown")
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        print(f"Wrote: {out_path}", file=sys.stderr)
        print("Microbench FAILED -- see collection_errors.", file=sys.stderr)
        if args.stdout:
            print(json.dumps(payload, indent=2, default=str))
        return 1

    metrics["microbench"] = summarize_errors(intervals, args.interval)

    if args.with_flip_stats:
        flip = collect_flip_stats(errors, args.flip_frames)
        metrics["flip_stats"] = flip  # None if the probe could not run
    else:
        metrics["flip_stats"] = None

    metrics["_had_errors"] = bool(errors)
    verdict = derive_verdict(metrics, args.interval)
    metrics.pop("_had_errors", None)

    payload = build_envelope(
        schema_name=SCHEMA_NAME,
        schema_version=SCHEMA_VERSION,
        machine=machine,
        blocks={"metrics": metrics},
        verdict=verdict,
        errors=errors,
    )

    out_path = args.out or default_output_path(
        out_base, os_segment(machine), machine.get("hostname", "unknown")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print(f"Verdict: {verdict['category']}", file=sys.stderr)
    print(f"Wrote: {out_path}", file=sys.stderr)
    if errors:
        print(
            f"Collection errors: {len(errors)} (see JSON 'collection_errors')",
            file=sys.stderr,
        )

    if args.stdout:
        print(json.dumps(payload, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
