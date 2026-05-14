# Timing-test recording: current state audit

Step 1 of #761 ("Re-baseline booth timing tests for Win10/Win11 comparison"). Captures the operator path, the post-processing surface, and the gaps that have to close before a Win10/Win11 A/B baseline is even possible. Concern #3 of #759.

Strictly an audit — no code changes here. The follow-up steps (parametrize, metrics, microbenchmark wiring, comparator, baseline lockdown) stay in #761 and will be tracked as separate PRs once this doc's findings are agreed.

## TL;DR

- The timing-test **recording** path is essentially undocumented. The only callable entry point in this repo is `saccades_sounds.test_script()` — single-machine, runs the saccades-with-sound stimulus alone, does **not** record any of the 12 production devices that `timing_test_obs` actually expects.
- The full production recording path is presumed to go through the CTR GUI plus deployed yaml task configs that live outside this repo, but no doc captures that path and no string in `neurobooth_os/` cross-references the task class to the GUI's task loader.
- A second task class, `audio_video_test.Timing_Test`, has **no callers, no `__main__`, no test wrapper**. It exists but is unreachable from any code path I can find.
- The **post-processing** surface is six orphan scripts under `extras/`, all from 2022, all carrying hardcoded `Z:\data` / `Z:\processed_data` paths and at least one carrying a hardcoded session id from `2022-11-09`. None are exercised by any test or CI step.
- Two orphan **clock-primitive microbenchmarks** exist (`time_clocks.py`, `time_clocks_variance.py`) but are not wired into any driver.
- The two `.bat` files in `tests/deployment-test/` are post-processing drivers, **not recording drivers**. They use `python -i` so they drop to an interactive REPL after the script runs — unsuitable for unattended baseline runs.

The harness rebuild proposed by #761 is justified — the existing code cannot produce comparable Win10 vs Win11 numbers and would not, even if the recording path were documented.

## 1. Recording entry points

### 1.1 The only callable Python entry point

`neurobooth_os/tasks/test_timing/saccades_sounds.py:94-98`

```python
def test_script() -> None:
    from neurobooth_os.iout.metadator import read_stimuli
    kwargs = read_stimuli()['timing_test_task_1'].model_dump()
    task = Saccade_synch(**kwargs)
    task.run(show_continue_repeat_slide=False)
```

This is the only entry point that:

1. Names a specific timing-test config (`timing_test_task_1`)
2. Instantiates a concrete task class (`Saccade_synch`)
3. Has a `__main__` block to make it runnable

What it does NOT do:

- It does not start any LSL device recording — no Intel D455, FLIR, Eyelink, Mic, Mbient, or iPhone capture is initiated.
- It only runs the stimulus and the marker stream from the calling machine (typically STM in production).
- It depends on `timing_test_task_1` being defined in the operator's **deployed** stimuli yaml (per `read_stimuli()` → `_parse_files('stimuli')` → `get_cfg_path('stimuli')` in `neurobooth_os/iout/metadator.py:637`). No yaml in this repo defines it.

So `python -m neurobooth_os.tasks.test_timing.saccades_sounds` would either error (config missing) or run the stimulus alone — neither produces the multi-device recording that the post-processing scripts expect.

### 1.2 Orphan task class

`neurobooth_os/tasks/test_timing/audio_video_test.py` defines `Timing_Test`, which opens a full-screen PsychoPy window and runs 10 iterations of "draw white rectangle + play 1000Hz tone + wait 1s". Useful self-contained stimulus, **but**:

- No `__main__` block.
- No `test_script()` function.
- `grep -r 'Timing_Test\|audio_video_test'` across the repo finds only the file itself — no importers, no callers, no test wrappers, no GUI registration.

The class exists; the path to invoke it does not.

### 1.3 The implied production path (not documented anywhere)

`examples/split_task_device_map.yml:290-302` lists `timing_test_obs` as a known production task ID with the full 12-device recording fan-out:

```yaml
timing_test_obs:
- Intel_D455_1
- Intel_D455_2
- Intel_D455_3
- Mbient_LH_2
- Mbient_RH_2
- Mbient_RF_2
- Mbient_LF_2
- Mbient_BK_1
- FLIR_blackfly_1
- Mic_Yeti_dev_1
- Eyelink_1
- IPhone_dev_1
```

This is what the post-processing scripts in `extras/` were written against (they glob `*timing_test_obs_intel{1,2,3}.bag`, `*timing_test_obs_FLIR*`, `*timing_test_obs_IPhone*`, etc.).

**Inferred operator path** (no doc states this; reconstructed from the yaml convention):

1. Operator launches the CTR GUI on the control machine.
2. GUI loads tasks / stimuli / collections / studies from yaml files in the operator's deployed config directory (resolved via `get_cfg_path()` in `metadator.py`).
3. The deployed `tasks/timing_test_obs.yml` (not in this repo) presumably wires the task to a stimulus that ultimately resolves to `Saccade_synch` via `stimulus_file:` (the field defined in `iout/stim_param_reader.py:548`).
4. The deployed `collections/<something>.yml` or `studies/<something>.yml` includes `timing_test_obs` as one of its tasks.
5. Operator selects that study / collection, picks a subject id, hits Start. ACQ and STM record the listed devices; the stimulus runs on STM.
6. XDF and per-device HDF5 files land in the operator's data directory (`Z:\data` historically, possibly different on the current booths).

**Sibling task variants observed in the same yaml** (lines 304-317):

- `saccades_horizontal_obs_test` — FLIR + Eyelink + iPhone only
- `pursuit_test_obs_1` — same three
- `pursuit_test_obs_test` — same three

The `_test` suffix suggests these are reduced-device variants for timing-test sweeps. There is no doc explaining when to use which.

### 1.4 What is provably missing from "how do I record a timing test"

| Question | State |
|---|---|
| Which study or collection contains `timing_test_obs`? | Unknown from this repo. Lives in the operator's deployed yaml. |
| What duration is a "standard" timing-test recording? | Undefined. `Saccade_synch.run_trials()` runs `n_trials × 4 transitions × wait_center` seconds — all from the `timing_test_task_1` yaml, which we cannot see. |
| What scene / lighting conditions? | Undefined. No fixture or doc. |
| Is the operator expected to wear noise-cancelling headphones? Stand still? Sit? | Undefined. |
| Should ambient light be controlled? | Undefined (the RealSense mean-RGB analysis is photometric; ambient light matters). |
| What is the expected post-conditions of a "good" recording? | Undefined. No acceptance criteria. |

Without these, two operators on two OSes cannot produce comparable recordings — and that, not the code, is the load-bearing gap.

## 2. Post-processing surface

### 2.1 Bat drivers (in `tests/deployment-test/`)

| Bat | What it actually does | Win11 risk |
|---|---|---|
| `run_timing_tests.bat` | `python -i extras/synch_frame_mean_rgb.py` (post-processing, not recording) | None new; `python -i` drops to a REPL after the script runs, unsuitable for unattended runs. Already-flagged by #766's bat audit conclusions but excluded from that audit's scope because #761 owns the rewrite. |
| `run_timing_tests_plotting.bat` | `python -i extras/plot_timing_test_sync.py -- -i "100064_2022-11-09" -t "_20h-02m-48s"` | Same `python -i` REPL issue. **Hardcoded session id and time from 2022** — a Win11-pilot operator would unintentionally re-plot a Win10 session from 2022. |

### 2.2 Extras scripts (all 2022 vintage; all hardcoded `Z:\` paths)

| Script | Purpose | Hardcoded inputs |
|---|---|---|
| `extras/synch_frame_mean_rgb.py` | RealSense `.bag` → mean-RGB HDF5 for 3 cameras. Walks `Z:/data/*/*timing_test_obs_intel{1,2,3}.bag`. | `Z:/data`, `Z:/processed_data` in `__main__` |
| `extras/synch_frame_mean_rgb_flir_iphone.py` | Same shape for FLIR and iPhone. | Same convention. |
| `extras/plot_timing_test_sync.py` | Main visualization. Normalizes per-device traces (Eyelink, Mic, Intel D455 ×3, FLIR, iPhone) on a shared axis. | `Z:\data`, `Z:\processed_data`, optparse defaults `100064_2022-09-28` / `_14h-54m-26s`. |
| `extras/plot_iphone_audio_video_rgb.py` | Alt plotter, focused on the iPhone audio↔video↔RGB alignment. | Module-level hardcoded session: `100064_2022-09-28_14h-54m-26s`. Not parameterized at all. |
| `extras/convert_bag2vid_timestamps.py` | bag → CSV of frame timestamps. | Probably `Z:/`-shaped; lives in the same chain. |
| `extras/clapping_test_plotting.py` | Plotting for `clapping_test_obs` (a different timing-test variant). | Same style. |

Known bugs in `plot_timing_test_sync.py` (already called out in the #761 issue body, confirmed by reading the file):

- The Mic block is gated `if chunk_len % 2:` (line 166). Even chunk lengths silently skip the audio-clock plot. Looks inverted.
- The `Mbient_RH` branch (line 139) duplicates the Eyelink branch with `_get_target_traces`, which is wrong for IMU data. Even if it triggered, it would mis-plot.

### 2.3 Microbenchmarks (no caller anywhere)

| Script | What it measures | How it emits |
|---|---|---|
| `extras/time_clocks.py` | Total wall time of 10000 × 0.5 ms busy-waits using `pylsl.local_clock`, `time.time`, `time.sleep`, `psychopy.core.wait`, `psychopy.core.wait` with `hogCPUperiod` | Five `print()` lines |
| `extras/time_clocks_variance.py` | Same five primitives, 100 reps, per-iteration error | One `print()` line per primitive with mean/SD |

Neither is invoked by any `.bat`, any test, any GUI path, or any other script in the repo. Both are 2022-vintage standalone scripts last touched as part of the original timing investigation.

## 3. Gaps for the Win10 / Win11 A/B comparison

Crossing the audit findings with #761's "What 'adequate' should mean" list:

| Gap | Source |
|---|---|
| No documented operator path for producing a timing-test recording | §1.4 above |
| No fixed-parameter recording fixture (duration, scene, lighting, expected post-conditions) | §1.4 above |
| Hardcoded `Z:\` paths in every post-processing script | §2.2 |
| Hardcoded 2022 session id in the plotting bat | §2.1 |
| Visual-only output (no per-device numeric metrics — mean/SD/p95/p99 frame interval, dropped frames, target-onset → trace-onset latency, clock drift) | §2.2 |
| No A/B comparator that ingests two runs and emits a delta with pass/fail thresholds | absent entirely |
| No per-run metadata tagging (OS build, GPU driver, Python version, `uv tree`, machine name, date) | absent entirely |
| Microbenchmarks orphaned from any driver | §2.3 |
| Audio-clock plot bug (inverted `if chunk_len % 2`) | §2.2 |
| Mbient plotting branch copy-pasted from Eyelink | §2.2 |
| `python -i` drops to interactive REPL — incompatible with unattended N-repeated-run sweeps | §2.1 |

## 4. Suggested follow-up

Steps 2–6 of #761's suggested approach map cleanly onto the gaps above and could each be a small PR or a sibling issue. Rough sizing:

1. **Parametrize post-processing** — 1 PR. Remove all `Z:\` hardcodes and the 2022 session id from `plot_timing_test_sync.py`, `synch_frame_mean_rgb.py`, `synch_frame_mean_rgb_flir_iphone.py`, `plot_iphone_audio_video_rgb.py`. Add `--data-dir`, `--processed-dir`, `--session-id`, `--session-time` flags. Fix the audio-clock and Mbient plotting bugs along the way.
2. **Metrics emitter** — 1 PR. New `extras/perf/timing_test_metrics.py` (or in `tests/deployment-test/`) that takes the same inputs as the plotter and emits a JSON artefact tagged with OS build, GPU driver, Python version, etc., per-device frame-interval statistics and clock drift.
3. **Microbenchmark integration** — 1 PR. Refactor `time_clocks_variance.py` to emit JSON; add to the metrics-emitter pipeline so a single harness run captures both the recording-derived metrics and the microbench numbers.
4. **A/B comparator** — 1 PR. `compare_runs.py` that takes two metric JSONs, emits a delta table with explicit thresholds (jitter SD tolerance, dropped-frame regression rule, clock-drift ppm bound, microbench p99 multiplier).
5. **Documented recording fixture** — 1 PR or sibling issue. Document the operator's path to produce a timing-test recording (which study/collection to pick, what duration, what scene, what acceptance criteria) so two operators on two OSes can produce comparable inputs. This requires input from someone who runs the booth — pure code work is insufficient.
6. **Win10 baseline lockdown** — operator work, ≥3 runs per booth, commit JSONs under `extras/perf/baselines/timing/win10/` (matching the convention established by `extras/perf/baselines/win11_readiness/`). Must precede any Win11 comparison run.

Step 5 is the load-bearing one and is non-code work. Steps 1–4 can land in parallel as long as step 5 lands before step 6.

## References

- #759 — Win11 upgrade umbrella, concern #3 (timing)
- #761 — parent issue (this audit is its step 1)
- `neurobooth_os/tasks/test_timing/{saccades_sounds.py, audio_video_test.py, marker.py}`
- `neurobooth_os/iout/metadator.py:637` — `read_stimuli()` and the deployed yaml convention
- `neurobooth_os/iout/stim_param_reader.py:548` — `stimulus_file:` field that wires task IDs to Python classes
- `examples/split_task_device_map.yml:290-302` — `timing_test_obs` device fan-out
- `extras/synch_frame_mean_rgb.py`, `extras/plot_timing_test_sync.py` — primary post-processing scripts
- `tests/deployment-test/run_timing_tests*.bat` — current drivers (post-processing only)
- `extras/time_clocks.py`, `extras/time_clocks_variance.py` — orphan microbenchmarks
