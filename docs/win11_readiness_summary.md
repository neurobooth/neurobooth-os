# Windows 11 Readiness Summary

One-page roll-up of the per-booth Windows 11 minimum-hardware-floor inventory called for by issue #767 (concern #9 of #759).

The source of truth is the per-booth JSON in [`extras/perf/baselines/win11_readiness/`](../extras/perf/baselines/win11_readiness/), produced by [`extras/perf/win11_readiness.py`](../extras/perf/win11_readiness.py). This document summarizes those JSONs for humans; if the two ever disagree, the JSONs are authoritative.

## How to populate this doc

1. On each booth (CTR, STM, ACQ, plus any spare/staging hardware), open an **elevated** PowerShell (right-click → Run as Administrator) and run:

   ```
   uv run python extras/perf/win11_readiness.py --role <CTR|STM|ACQ|spare>
   ```

   Admin is required because `Confirm-SecureBootUEFI` and the `root\CIMV2\Security\MicrosoftTpm` namespace are ACL'd to Administrators. A non-elevated run returns a false `UPGRADEABLE` verdict with a misleading remediation hint, even on a booth that is genuinely `PASS`.

2. Commit the resulting `extras/perf/baselines/win11_readiness/<hostname>.json`.
3. Add a row to the table below; copy the `verdict.category` from the JSON.
4. For `UPGRADEABLE` booths, fill in the firmware-toggle notes section.
5. For `HARDWARE_FAIL` booths, fill in the escalation-log section.

## Verdict categories

| Category | Meaning | Next action |
|---|---|---|
| `PASS` | All checked floor items satisfied. CPU still needs manual cross-check against Microsoft's published Win11 supported-CPU list. | Eligible for the Win11 pilot (#769). |
| `UPGRADEABLE` | One or more items off but firmware-toggleable (TPM disabled, Secure Boot off, BIOS in Legacy mode). | Operator toggles in firmware; re-run script; expect `PASS`. |
| `HARDWARE_FAIL` | One or more items cannot be fixed without hardware replacement (TPM absent, TPM < 2.0, RAM < 4 GiB, system disk < 64 GiB). | Escalate to the lab-budget owner. |

CPU classification is not done by the script because Microsoft's supported-CPU list moves; the JSON carries the CPU name and ID for manual lookup against the current Intel / AMD pages.

## Booth inventory

| Booth role | Hostname | Verdict | Reasons (short) | JSON | Date captured |
|---|---|---|---|---|---|
| CTR | ctr | PASS | None (see CPU note below) | [ctr.json](../extras/perf/baselines/win11_readiness/ctr.json) | 2026-05-14 |
| STM | stm | PASS | None (see CPU note below) | [stm.json](../extras/perf/baselines/win11_readiness/stm.json) | 2026-05-14 |
| ACQ | acq | PASS | None (see CPU note below) | [acq.json](../extras/perf/baselines/win11_readiness/acq.json) | 2026-05-14 |

**CPU compatibility (manual check):** the script appends `"CPU not auto-classified -- compare CPU name to Microsoft's Win11 supported list"` to every verdict's `reasons` array by design (Microsoft's list moves and is not hard-coded). All three booth CPUs were verified against Microsoft's published Win11 supported-CPU list:

- CTR: `Intel(R) Core(TM) i7-10700` (10th-gen Comet Lake) — supported
- STM: `Intel(R) Core(TM) i7-10700K` (10th-gen Comet Lake) — supported
- ACQ: `Intel(R) Core(TM) i7-10700K` (10th-gen Comet Lake) — supported

All other floor items (TPM 2.0 present + enabled + activated, Secure Boot supported + enabled, BIOS in UEFI mode, RAM ≥ 4 GiB, system disk ≥ 64 GiB free) are verified in the per-booth JSONs above. None of the booths required firmware toggles or hardware replacement.

## Firmware toggles for UPGRADEABLE booths

All booths passed at first elevated run; no firmware-toggle work needed.

## Escalation log for HARDWARE_FAIL booths

All booths passed; no escalation needed.

## Out of scope

- Doing the actual TPM / Secure Boot enablement in firmware on each booth — operator work.
- Driver refreshes — handled separately under #763.
- The decision to upgrade — that follows from this data plus the harness results in #761 / #762 / #763 / #764 and the Win11 pilot in #769.
