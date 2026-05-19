# Timing Baseline Summary

One-page roll-up of the booth timing-regression instrument called for by
issue #761 (concern #3 of #759). It answers one question: **did recording
timing regress between Windows 10 and Windows 11?**

The source of truth is the per-artefact JSON under
[`extras/perf/baselines/timing/`](../extras/perf/baselines/timing/), produced
by the three tools below. This document summarizes those JSONs for humans;
**if the doc and a JSON ever disagree, the JSON wins** (same convention as
[`win11_readiness_summary.md`](win11_readiness_summary.md)).

Strategy and rationale live in
[`timing_test_strategy.md`](timing_test_strategy.md); the code-state audit is
[`timing_test_recording_audit.md`](timing_test_recording_audit.md). This is
the operational roll-up only.

## The instrument

| Tool | Strategy test | What it produces | Lab needed |
|---|---|---|---|
| [`extras/perf/timing_baseline.py`](../extras/perf/timing_baseline.py) | **C** (clock microbench) + optional flip-jitter probe | `<log_dir>/timing/<os>/<hostname>.json` — per-primitive mean/SD/p95/p99/max error; optional PsychoPy flip-interval jitter + dropped flips | No |
| [`extras/perf/timing_session_metrics.py`](../extras/perf/timing_session_metrics.py) | **D** (passive session metrics) | `<log_dir>/timing/session_ab_*.json` — Win10-vs-Win11 A/B from the production DB: cross-device start skew, marker→first-sample latency, per-device coarse span | No (remote, SSH tunnel) |
| [`extras/perf/compare_timing.py`](../extras/perf/compare_timing.py) | A/B comparator (§6) | `<log_dir>/timing/compare_<hostname>.json` — every raw delta between a locked Win10 baseline and a Win11 pilot, plus a flagged-for-review verdict | No |

`<log_dir>` is the neurobooth config `local_log_dir` (same place the
crash/startup logs go), with an `NB_INSTALL` → home fallback — resolved via
`neurobooth_os.log_manager._get_log_dir`. Run artefacts deliberately stay
**out of the repo working tree**; `--out` / `--json` override the path.
"Locking" a baseline is the explicit step of copying a chosen run into the
version-controlled `extras/perf/baselines/timing/` tree and committing it.

`timing_baseline.py` and `compare_timing.py` are the routine loop (C). It is
quantitative, replicable, remote, and auto-summarized. `timing_session_metrics
.py` is the representative corroborator (D) — see "Known limits".

## How to populate this doc (the #759 phased plan)

Execution is tracked, per site, in **#801** (parent) → **#802 Merrimack**,
**#803 Wang**, **#804 CTRU**. The procedure below is the summary; those
issues are the checklist.

### Phase 2 — lock the Win10 baseline (do this *before* any Win11 work)

1. On each booth machine (CTR, STM, ACQ, plus any spare), on the **current
   Win10** install, booth otherwise idle (GUI closed, no recording):

   ```
   uv run python extras/perf/timing_baseline.py --role <CTR|STM|ACQ|spare>
   ```

   This writes to `<log_dir>/timing/win10/<hostname>.json` (the config log
   dir, **not** the repo). Repeat **≥3 times per machine** so single-run
   noise does not masquerade as an OS effect.

2. Optionally add the display-jitter probe (needs a display, best-effort):

   ```
   uv run python extras/perf/timing_baseline.py --role STM --with-flip-stats
   ```

3. Capture the historical-session A/B baseline remotely (zero booth time):

   ```
   uv run python extras/perf/timing_session_metrics.py \
       --baseline-from <win10-window-start> --baseline-to <win10-window-end> \
       --pilot-from <placeholder> --pilot-to <placeholder>
   ```

   Writes `<log_dir>/timing/session_ab_<...>.json`.

4. **Lock it.** Pick the cleanest microbench run per machine (verdict
   `CAPTURED`, no `collection_errors`), copy that JSON from the log dir into
   `extras/perf/baselines/timing/win10/<hostname>.json`, and commit. Do the
   same for the session-metrics JSON. This copy-and-commit is the only step
   that puts a run under version control — deliberate, not automatic.

5. Fill in the **Win10 baseline** table below from the committed JSONs.

### Phase 3 — Win11 pilot diff

1. On the Win11 pilot booth, re-run step 1 (it auto-writes under
   `<log_dir>/timing/win11/<hostname>.json`); lock it into
   `extras/perf/baselines/timing/win11/<hostname>.json`.
2. Diff the two locked baselines:

   ```
   uv run python extras/perf/compare_timing.py \
       extras/perf/baselines/timing/win10/<hostname>.json \
       extras/perf/baselines/timing/win11/<hostname>.json
   ```

   The delta JSON lands in `<log_dir>/timing/compare_<hostname>.json`; lock
   it alongside the baselines if you want it version-controlled.
3. Re-run `timing_session_metrics.py` with the real `--pilot-*` window.
4. Fill in the **Win10→Win11 comparison** table; a `REVIEW` verdict means a
   human inspects the flagged numbers — it is **not** a failure.

## Verdict categories

| Tool | Category | Meaning |
|---|---|---|
| `timing_baseline` | `CAPTURED` | Clean single-run capture. A single run never says "regressed" — that needs the comparator. |
| `timing_baseline` | `CAPTURED_WITH_ERRORS` | Captured, but `collection_errors` present (e.g. flip probe unavailable). Usable; read the errors. |
| `compare_timing` | `MATCH` | No proposed threshold tripped. Raw deltas are still printed in full. |
| `compare_timing` | `REVIEW` | ≥1 proposed threshold tripped → a human reviews with the numbers in hand. Never auto-fail. |
| `timing_session_metrics` | `CAPTURED` | Tier-1 DB A/B captured. Sample-level metrics are deferred (see `metrics.sample_level`). |

Thresholds in `compare_timing.py` (jitter-SD ratio, microbench-p99 ratio,
new-dropped-flips) are **proposals to be ratified by whoever owns the timing
budget, not measured facts**, and every one is CLI-overridable. Raw deltas
are printed regardless of whether a threshold trips.

## Win10 baseline

_Not yet captured — Phase 2 is operator work (≥3 runs per booth). No numbers
are entered here until the JSONs are committed; this table is the shape, not
data._

| Booth | Hostname | Verdict | Microbench p99 (worst primitive) | Flip SD (ms) | JSON | Date |
|---|---|---|---|---|---|---|
| CTR | _ctr_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| STM | _stm_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| ACQ | _acq_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |

## Win10 → Win11 comparison

_Not yet run — Phase 3 follows the Win11 pilot (#769). Populated from
`compare_timing.py` output._

| Booth | OS transition | Verdict | Flags | Comparison JSON | Date |
|---|---|---|---|---|---|
| CTR | _Win10 → Win11_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| STM | _Win10 → Win11_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |
| ACQ | _Win10 → Win11_ | _(pending)_ | _(pending)_ | _(pending)_ | _(pending)_ |

## Known limits (read before relying on this)

These are stated plainly because the strategy doc requires it, not buried:

1. **Test D is a corroborator, not the causal instrument.** Comparing
   sessions across calendar time confounds the OS with subjects, room,
   driver versions, software release, and USB/BLE wear (strategy §6.1.2).
   The microbench (C) is the clean causal probe; if C and D disagree, that
   disagreement is signal.
2. **Sample-level jitter / native-vs-LSL drift (ppm) / dropped-duplicated
   frames are deferred.** Those need the per-device HDF5 sample timestamps
   (not in Postgres) and a methodology review before any number is trusted
   (strategy §6.1.1). `timing_session_metrics.py` emits an explicit
   `deferred` sentinel for them rather than a fabricated value.
3. **Absolute end-to-end analog latency (G2) cannot be measured remotely.**
   It needs a physical sensor in the loop and is measured **once per OS
   baseline, not every run** (strategy §7). A hardware sync box would make
   it cheap but is net-new procurement, out of scope here.

## Deferred / out of scope (intentionally not built)

- **The heavyweight bag-file post-processing rebuild** (#761 step 2 / audit
  §4 step 1: de-hardcode the 2022 `Z:\` scripts, fix the two
  `plot_timing_test_sync.py` bugs). The strategy demotes the
  saccades/clapping tests to a **one-time confirmatory run per OS baseline**,
  so rebuilding that pipeline is deliberately not part of the routine loop.
- **The documented recording fixture** — defined in
  [`timing_test_recording_audit.md`](timing_test_recording_audit.md) **§4
  item 5** and **§1.4** (which study/collection, duration, scene, lighting,
  operator posture, acceptance criteria for the one confirmatory physical
  run). It is non-code work requiring input from someone who runs the booth,
  and it gates only the physical saccades run — **not** the C+D routine
  loop. (Note: issue #761's *body* numbers its suggested approach
  differently; the audit doc §4 / the #761 audit comment are the
  authoritative numbering for this item.)
- **The actual Win10 baseline capture and Win11 pilot runs** — operator
  work, tracked in **#801** (→ #802 Merrimack, #803 Wang, #804 CTRU) and
  #769; scheduled against real booths.

## References

- Strategy: [`timing_test_strategy.md`](timing_test_strategy.md)
- Audit: [`timing_test_recording_audit.md`](timing_test_recording_audit.md)
- Convention mirrored: [`win11_readiness_summary.md`](win11_readiness_summary.md)
- Change-over-time table format precedent:
  [`perf/inter-task times [2026-04-03].md`](perf/inter-task%20times%20%5B2026-04-03%5D.md)
- Issues: #759 (umbrella, concern #3), #761 (this harness), #801 (Win10
  baseline execution → #802 Merrimack, #803 Wang, #804 CTRU), #769 (Win11
  pilot)
