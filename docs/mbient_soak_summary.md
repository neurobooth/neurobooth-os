# Mbient Soak Summary

One-page roll-up of the active Mbient/BLE soak harness called for by issue
#762 (concern #4 of #759). It answers one question: **does the Mbient/BLE
stack behave the same — or crash differently — between Windows 10 and
Windows 11?**

The source of truth is the per-run JSON under
[`extras/perf/baselines/mbient_soak/`](../extras/perf/baselines/mbient_soak/),
produced by the tools below. This document summarizes those JSONs for
humans; **if the doc and a JSON disagree, the JSON wins** (same convention as
[`timing_summary.md`](timing_summary.md) / `win11_readiness_summary.md`).

## The instrument

| Tool | Produces | Lab needed |
|---|---|---|
| [`extras/perf/mbient_soak.py`](../extras/perf/mbient_soak.py) | `<log_dir>/mbient_soak/<os>/<host>_<ts>.json` — per-cycle connect/reset timing, sample drop-rate, BLE disconnects, and the **native-crash exit code** over a multi-hour connect/stream/reset/reconnect soak | Yes (real BLE devices on one ACQ-class booth) |
| [`extras/perf/mbient_soak_compare.py`](../extras/perf/mbient_soak_compare.py) | `<log_dir>/mbient_soak/compare_<host>.json` — every raw delta between a locked Win10 run and a Win11 run, plus a flagged-for-review verdict | No |

It drives the **production** `neurobooth_os.iout.mbient.Mbient` surface
(`connect`→`start`→`reset_and_reconnect`→`close`); LSL/DB are neutralized at
the harness boundary, `mbient.py` is untouched. The retrospective
`extras/perf/mbient_timing*.py` / `mbient_acq_bottleneck.py` scripts are kept
as-is — this is additive.

`<log_dir>` is the neurobooth config `local_log_dir` (`NB_INSTALL` → home
fallback). Runtime artefacts stay **out of the repo working tree**; a locked
baseline is a deliberate copy into `extras/perf/baselines/mbient_soak/`.

## How to populate this doc

Win10-baseline execution across all four Win11-evaluation harnesses
(timing, **this Mbient soak**, hardware/SDK, WMI/DCOM) is coordinated under
**#768**. The procedure below is the summary; #768 is the checklist.

### Phase 2 — lock the Win10 baseline (before any Win11 work)

1. On an ACQ-class booth with the real Mbients, current Win10, booth idle:

   ```
   uv run python extras/perf/mbient_soak.py --json %USERPROFILE%\mbients.json \
       --duration-min 120 --wer-dumps
   uv run python extras/perf/mbient_soak.py --json %USERPROFILE%\mbients.json \
       --duration-min 120 --with-iphone --wer-dumps
   ```

   Run **≥3 times per arm** (with and **without** `--with-iphone` — both
   arms are required; see "Known limits"). Writes to
   `<log_dir>/mbient_soak/win10/...`.

2. **Lock it.** Pick the representative runs, copy them into
   `extras/perf/baselines/mbient_soak/win10/`, and commit. This copy-and-commit
   is the only step that version-controls a run.

3. Fill in the **Win10 baseline** table below from the committed JSONs.

### Phase 3 — Win11 pilot diff

1. On the Win11 pilot booth, re-run step 1 (auto-writes under
   `<log_dir>/mbient_soak/win11/...`); lock into
   `extras/perf/baselines/mbient_soak/win11/`.
2. Diff **matching arms** (with-iphone vs with-iphone, etc.):

   ```
   uv run python extras/perf/mbient_soak_compare.py \
       extras/perf/baselines/mbient_soak/win10/acq_withiphone.json \
       extras/perf/baselines/mbient_soak/win11/acq_withiphone.json
   ```
3. Fill in the **comparison** table; a `REVIEW` verdict means a human
   inspects the flagged numbers — it is **not** a failure.

## Verdict categories

| Tool | Category | Meaning |
|---|---|---|
| `mbient_soak` | `CAPTURED` | Clean soak, no Python errors, no native crash. |
| `mbient_soak` | `CAPTURED_WITH_ERRORS` | Soak completed but some cycles failed at the Python level (read `metrics.errors`). |
| `mbient_soak` | `CRASHED` | The worker process died on a native fault — the dominant Win10 failure mode. This is a **recorded data point, not a harness bug**; see `crash.dump_paths` / the faulthandler log. |
| `mbient_soak_compare` | `MATCH` | No proposed threshold tripped. Raw deltas still printed in full. |
| `mbient_soak_compare` | `REVIEW` | ≥1 proposed threshold tripped (or the #669 measurement trap detected) → a human reviews. Never auto-fail. |

Comparator thresholds (connect/reset p95 ratio, drop-rate increase,
ok-fraction drop) are **proposals to be ratified by whoever owns the BLE
budget, not measured facts**, and every one is CLI-overridable. Raw deltas
are printed regardless.

## Win10 baseline

_Not yet captured — Phase 2 is operator work on a real ACQ booth (≥3 runs
per arm). No numbers here until the JSONs are committed; this is the shape._

| Arm | Host | Verdict | connect p95 (ms) | reset p95 (ms) | drop-rate | crashed | JSON | Date |
|---|---|---|---|---|---|---|---|---|
| no-iphone | _acq_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| with-iphone | _acq_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |

## Win10 → Win11 comparison

_Not yet run — Phase 3 follows the Win11 pilot (#769)._

| Arm | OS transition | Verdict | Flags | Comparison JSON | Date |
|---|---|---|---|---|---|
| no-iphone | _Win10 → Win11_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| with-iphone | _Win10 → Win11_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |

## Known limits (read before relying on this)

1. **The iPhone co-runner is synthetic.** #669 — the native access
   violation that coincides with Mbient BLE-connect while the iPhone
   *listening thread* runs — is a two-subsystem race. Driving the real
   iPhone in a multi-hour soak would spew large video files into the
   permanent-storage transfer workflow, so `--with-iphone` runs a synthetic
   stand-in that reproduces the **contention shape** (a continuously
   blocking-socket listener thread concurrent with Mbient BLE) without an
   iPhone or any video. A clean Win11 `--with-iphone` result is therefore
   **suggestive, not definitive**. The run JSON records
   `run.iphone_corunner: "synthetic"`; the comparator refuses to call a
   crash-improvement meaningful unless both sides' co-runner state matched.
2. **Definitive #669 confirmation is a separate, manual booth check** — one
   short run with the *real* iPhone and the transfer/dump workflow disabled
   so it does not pollute permanent storage. Out of scope for the routine
   harness; noted here so it is tracked, not assumed.
3. **Negotiated BLE connection parameters are not recorded.** The production
   public surface exposes only the *requested* `ConnectionParameters`
   (7.5/7.5/0/6000). Capturing the negotiated interval/latency/timeout would
   require new native calls in `mbient.py` (out of scope, #762). The JSON
   records the requested values and flags this explicitly.
4. **Both arms are mandatory for a valid OS comparison.** A Win11 soak run
   only without the co-runner can look clean simply because it never
   exercised the #669 path — that is the measurement trap #762 point 5
   names. Always capture and diff matching arms.

## Deferred / out of scope (per #762, intentionally not built)

- **Fixing any crash the harness finds** — that becomes its own issue. This
  is a measurement tool.
- **Re-architecting `mbient.py`** to be driveable outside the GUI — the
  harness calls the existing public surface; it does not fork it.
- **Migrating off `mbientlab.warble` / `metawear`** — would invalidate any
  baseline.
- **Replacing the retrospective `extras/perf/mbient_timing*.py`** — kept
  as-is; the soak is additive.

## References

- Sibling harness: [`timing_summary.md`](timing_summary.md) (#761)
- Convention mirrored: `win11_readiness_summary.md`
- Issues: #759 (umbrella, concern #4), #762 (this harness), #768 (Win10
  baseline lockdown across all four harnesses), #669 (the iPhone↔Mbient
  native race), #769 (Win11 pilot)
