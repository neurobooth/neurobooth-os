# Locked Mbient soak baseline artefacts

Version-controlled JSON artefacts for the Mbient/BLE soak harness
(issue #762, concern #4 of #759; Win10-baseline execution coordinated under
#768).

**The tools do not write here by default.** `mbient_soak.py` and
`mbient_soak_compare.py` write runs to the configured neurobooth log
directory (`<local_log_dir>/mbient_soak/...`, with an `NB_INSTALL` → home
fallback) so multi-hour soak output — including large crash minidumps — stays
out of the repo working tree.

This directory is the destination for a **deliberately locked** baseline: the
operator reviews the runs in the log dir, picks the representative ones, and
*copies* them here and commits. Layout once populated:

```
baselines/mbient_soak/
  win10/<host>_<arm>.json    # locked Win10 soak (one per arm: with/without iphone)
  win11/<host>_<arm>.json    # locked Win11 pilot soak
  compare_<host>.json        # locked comparator delta (optional)
```

Capture **both arms** (`--with-iphone` and without) — a Win11 run only
without the co-runner can look clean simply because it never exercised the
#669 path. The `win10` / `win11` segment is chosen automatically from the OS
build (Win11 = build ≥ 22000).

These committed JSONs are the source of truth. The human roll-up is
[`docs/mbient_soak_summary.md`](../../../../docs/mbient_soak_summary.md); if
the two disagree, the JSON wins. The capture-and-lock procedure (and the
synthetic-co-runner caveat) is in that doc. Nothing is committed here until
Phase 2 (operator work on a real ACQ booth) is done — this README keeps the
directory tracked until then.
