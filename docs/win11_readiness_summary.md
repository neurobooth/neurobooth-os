# Windows 11 Readiness Summary

One-page roll-up of the per-booth Windows 11 minimum-hardware-floor inventory called for by issue #767 (concern #9 of #759).

The source of truth is the per-booth JSON in [`extras/perf/baselines/win11_readiness/`](../extras/perf/baselines/win11_readiness/), produced by [`extras/perf/win11_readiness.py`](../extras/perf/win11_readiness.py). This document summarizes those JSONs for humans; if the two ever disagree, the JSONs are authoritative.

## How to populate this doc

1. On each booth (CTR, STM, ACQ, plus any spare/staging hardware), run:

   ```
   python extras/perf/win11_readiness.py --role <CTR|STM|ACQ|spare>
   ```

2. Commit the resulting `extras/perf/baselines/win11_readiness/<hostname>.json`.
3. Add a row to the table below; copy the `verdict.category` and `verdict.reasons` from the JSON.
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
| _CTR_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| _STM_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |
| _ACQ_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ | _TBD_ |

## Firmware toggles for UPGRADEABLE booths

_Empty until first UPGRADEABLE booth is recorded. Format suggestion: one subsection per booth, listing the BIOS menu paths the operator used to enable TPM / Secure Boot / UEFI mode._

## Escalation log for HARDWARE_FAIL booths

_Empty until first HARDWARE_FAIL booth is recorded. Format suggestion: one subsection per booth, listing the failing requirement, the inferred replacement need (motherboard / CPU / whole machine), and the date the budget conversation started._

## Out of scope

- Doing the actual TPM / Secure Boot enablement in firmware on each booth — operator work.
- Driver refreshes — handled separately under #763.
- The decision to upgrade — that follows from this data plus the harness results in #761 / #762 / #763 / #764 and the Win11 pilot in #769.
