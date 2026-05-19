# Locked SDK-validation baseline artefacts

Version-controlled JSON for the device hardware/SDK validation suite
(issue #763, concern #5 of #759; Win10-baseline execution coordinated
under #768).

**The tools do not write here by default.** `sdk_inventory.py`, the
`*_smoke.py` scripts, `driver_signing_check.py`, `check_usb_topology.py
--json`, and `sdk_compare.py` write to the configured neurobooth log
directory (`<local_log_dir>/<schema>/...`, `NB_INSTALL` → home fallback) so
run output stays out of the repo working tree.

This directory is the destination for a **deliberately locked** baseline: the
operator reviews the runs in the log dir, picks the representative ones, and
copies them here and commits. Suggested layout once populated:

```
baselines/sdk/
  win10/<host>.sdk_inventory.json     win11/<host>.sdk_inventory.json
  win10/<host>.driver_signing.json    win11/<host>.driver_signing.json
  win10/<host>.usb_topology.json      win11/<host>.usb_topology.json
  win10/<host>.<dev>_smoke.json       win11/<host>.<dev>_smoke.json
  compare_<host>.json                 # optional locked sdk_compare delta
```

The `win10` / `win11` segment is chosen automatically from the OS build
(Win11 = build ≥ 22000). EyeLink is **not** here — its smoke test is the
booth-attached follow-up #807 (`pylink` is proprietary, unverifiable
off-booth).

These committed JSONs are the source of truth. The human runbook is
[`docs/win11_vendor_compat.md`](../../../../docs/win11_vendor_compat.md); if
the two disagree, the JSON wins. Nothing is committed here until Phase-2
operator capture is done — this README keeps the directory tracked until
then.
