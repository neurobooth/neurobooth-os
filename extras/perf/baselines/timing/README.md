# Timing baseline artefacts

Committed JSON artefacts for the Win10/Win11 timing-regression instrument
(issue #761, concern #3 of #759). Layout:

```
baselines/timing/
  win10/<hostname>.json   # timing_baseline.py on the locked Win10 install
  win11/<hostname>.json   # timing_baseline.py on the Win11 pilot
  session_ab_*.json        # timing_session_metrics.py DB A/B (optional)
  compare_<hostname>.json  # compare_timing.py delta (optional)
```

`<hostname>` and the `win10` / `win11` segment are chosen automatically by
`extras/perf/timing_baseline.py` from the OS build (Win11 = build ≥ 22000).

These JSONs are the source of truth. The human roll-up is
[`docs/timing_summary.md`](../../../../docs/timing_summary.md); if the two
disagree, the JSON wins. Capture procedure is in that doc (the #759 phased
plan). Nothing is committed here until Phase 2 (operator work, ≥3 runs per
booth) is done — this README keeps the directory tracked until then.
