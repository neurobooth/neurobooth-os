# Locked timing baseline artefacts

Version-controlled JSON artefacts for the Win10/Win11 timing-regression
instrument (issue #761, concern #3 of #759; execution tracked in #801).

**The tools do not write here by default.** `timing_baseline.py`,
`timing_session_metrics.py`, and `compare_timing.py` write their runs to the
configured neurobooth log directory (`<local_log_dir>/timing/...`, with an
`NB_INSTALL` → home fallback) so routine run output stays out of the repo
working tree.

This directory is the destination for a **deliberately locked** baseline:
the operator reviews the runs in the log dir, picks the cleanest, and
*copies* it here and commits it. Layout once populated:

```
baselines/timing/
  win10/<hostname>.json    # locked Win10 microbench baseline
  win11/<hostname>.json    # locked Win11 pilot
  session_ab_*.json        # locked timing_session_metrics DB A/B
  compare_<hostname>.json  # locked compare_timing delta (optional)
```

`<hostname>` and the `win10` / `win11` segment are chosen automatically by
`timing_baseline.py` from the OS build (Win11 = build ≥ 22000).

These committed JSONs are the source of truth. The human roll-up is
[`docs/timing_summary.md`](../../../../docs/timing_summary.md); if the two
disagree, the JSON wins. The capture-and-lock procedure is in that doc (the
#759 phased plan / #801). Nothing is committed here until Phase 2 (operator
work, ≥3 runs per machine) is done — this README keeps the directory tracked
until then.
