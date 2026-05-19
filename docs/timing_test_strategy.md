# Timing-test strategy: goals, the existing tests, and a low-effort path

Audience: neurobooth lead, deciding how to validate recording timing across the
Windows 10 → Windows 11 upgrade (issue #759 umbrella, concern #3, tracked in
#761). This document answers four questions:

1. What are the timing tests actually *for*?
2. What does each existing test do, in detail?
3. How important is each, specifically for the Win10/Win11 question?
4. Can the work be made remote, automated, quantitative, and replicable — and
   if some part of it genuinely cannot, where exactly is that line?

It is a **strategy and feasibility** document. It does not change code. The
companion [`timing_test_recording_audit.md`](timing_test_recording_audit.md)
owns the *code-state* picture (what exists, what is orphaned, what is broken);
this document owns *what we should run, why, and whether the low-effort approach
is viable*. Where the two overlap, the audit is the authority on code state.

> **Bottom line up front.** For the question that actually matters for #759 —
> *"did recording timing regress between Win10 and Win11?"* — a remote,
> automated, quantitative suite is achievable and is the right primary
> instrument. It is built almost entirely from patterns the repo already
> proves out. The **two tests you remember (the rubber-band/tap test and the
> flashing-dots test) are the wrong instruments for routine regression work**:
> they are the only two that require a lab visit, and one of them also requires
> reconfiguring the booth and produces a multi-GB bag file. Exactly one timing
> property — the *absolute* photons-/sound-to-sample latency — cannot be
> measured remotely by anything we have. That property is also the *least*
> likely to move across an OS upgrade on unchanged hardware. The honest
> recommendation is to measure it **once per OS baseline, not every run**, and
> to treat everything else as automated. Section 7 states the limits without
> softening them.

---

## 1. What the timing tests are for

Neurobooth records on the order of a dozen devices at once (3 Intel D455, 5
Mbient IMUs, FLIR Blackfly, Yeti microphone, EyeLink, iPhone — the production
fan-out for the timing tasks is enumerated in
`examples/split_task_device_map.yml:276-302`). Every device timestamps its
samples onto a shared Lab Streaming Layer (LSL) clock. The scientific value of
the dataset depends entirely on being able to put a sample from one device next
to a sample from another and trust that "same timestamp" means "same moment."

The timing tests exist to validate, and to detect regressions in, five
properties:

| ID | Property | Plain-language question |
|----|----------|-------------------------|
| **G1** | Cross-device synchronization | Do two devices that saw the same instant get (nearly) the same LSL timestamp, with a small, stable, known offset? |
| **G2** | End-to-end latency | From a real event (photon, sound, limb motion) to the timestamp on the sample that captured it — what is the fixed delay, per device? |
| **G3** | Sampling regularity / jitter | Does each device actually deliver samples at its nominal rate — bounded jitter, no dropped or duplicated frames, no clock drift over a session? |
| **G4** | Stimulus-to-data alignment | When a marker says "stimulus at T," did the stimulus physically happen at T (display/audio presentation latency *and its variance*)? |
| **G5** | **Regression detection across a change** | After an OS upgrade / driver update / hardware swap, did any of G1–G4 move — by how much, which direction, is it within tolerance? |

G5 is the entire reason this is on the #759 critical path. The booths run
Win10; replacement hardware ships Win11; PsychoPy display timing under the
Win11 Desktop Window Manager (DWM) compositor, the LSL software clock, and the
USB/BLE stacks are all OS-sensitive. The question is not "is timing good in the
absolute" — it has been validated historically — it is **"did it change?"**
That reframing matters: a *difference* measurement against a locked Win10
baseline is far cheaper and more sensitive than re-deriving absolute latency
from scratch, and most of the difference signal is reachable without a lab.

Why this gates the dataset: if G1/G2 drift silently, every cross-device
analysis (IMU-onset vs gaze, audio onset vs video, etc.) is biased by the drift
amount, and the bias is invisible in the data itself. Timing validation is the
thing that lets the rest of the data be trusted.

---

## 2. The tests, in detail

There are **four** distinct ways timing is, or can be, measured here. You
described the two heavyweight physical ones. The other two already exist in the
repo in latent form and are the key to the low-effort path, so they are
documented at equal depth.

### 2.1 Test A — "Flashing dots / saccades-with-sound" (`timing_test_obs`)

**This is the one you described as flashing dots, requiring an Intel camera to
be repointed at the screen, and producing a very large bag file.** It is not
the "clapping" test; it is the saccades-with-synchronized-tone test.

**Stimulus.** `neurobooth_os/tasks/test_timing/saccades_sounds.py`, class
`Saccade_synch`. Per trial it cycles a target through four positions
`[(0,0), (-480,0), (0,0), (480,0)]` and the full screen through a colour
sequence (`saccades_sounds.py:50`, `:46-48`). At each transition it:

- draws the target and sets the new screen colour,
- schedules a tone to play *exactly at the next screen flip*
  (`tone.play(when=self.win.getFutureFlipTime(clock="ptb"))`,
  `saccades_sounds.py:69-70`),
- flips the window,
- sends LSL markers: `marker_task_start` / `marker_trial_start` /
  `send_target_loc` (`saccades_sounds.py:63,72-73,84`),
- busy-waits `wait_center` seconds on `pylsl.local_clock`
  (`saccades_sounds.py:14-19,75`).

The marker stream itself is a string LSL stream that also embeds a wall-clock
timestamp in the payload (`tasks/test_timing/marker.py:9-22`,
`"Stream-created_0_{time.time()}"`).

**What it uniquely measures.** A full-screen colour change is a bright,
unambiguous visual event with a *known stimulus-clock time* (the marker). A
camera physically repointed from the subject to the screen records the
luminance step; the microphone records the tone that was bolted to the same
flip; EyeLink records the saccade. Comparing marker time vs. camera
mean-RGB-step time vs. mic-onset time vs. gaze-onset time yields **G2
(absolute display + audio → capture latency)** and **G4 (stimulus-to-data
alignment)**, plus per-camera frame jitter (G3) and cross-device skew (G1).
Nothing else we have measures absolute display latency at all.

**How it is run today.** Per `timing_test_recording_audit.md` §1.3 the
production path is *inferred, not documented*: an operator launches the CTR
GUI, selects a study/collection whose deployed YAML wires `timing_test_obs` to
`Saccade_synch`, repoints an Intel D455 at the screen, and records all 12
devices. The deployed YAML that wires this is **not in the repo**. The only
in-repo entry point, `saccades_sounds.test_script()`
(`saccades_sounds.py:94-98`), runs the *stimulus alone* with no device capture
and needs a `timing_test_task_1` config that no in-repo YAML defines.

**What it outputs today.** Raw RealSense `.bag` files (a multi-GB artifact
— raw depth+RGB of a screen), post-processed by 2022-vintage scripts
with hardcoded `Z:\data` / `Z:\processed_data` paths and a hardcoded 2022
session id (`extras/synch_frame_mean_rgb.py`,
`extras/synch_frame_mean_rgb_flir_iphone.py`,
`extras/convert_bag2vid_timestamps.py`, `extras/plot_timing_test_sync.py:44,54`).
Output is a **visual matplotlib overlay**, normalized per device, read by eye.
It contains two known bugs (audit §2.2): an inverted `if chunk_len % 2` audio
gate (`plot_timing_test_sync.py:166`) and an Mbient branch copy-pasted from the
EyeLink branch (`plot_timing_test_sync.py:139-159`). There is **no numeric
metric and no Win10/Win11 comparator**.

**Effort profile.** Lab visit • booth reconfiguration (repoint a camera that is
normally on the subject) • multi-GB bag per run • manual/REPL post-processing
(`tests/deployment-test/run_timing_tests*.bat` use `python -i`) • eyeball
output. This is the single heaviest test and one to avoid running routinely.

### 2.2 Test B — "Rubber band / tap" (`clapping_test_obs`)

**This is the test with a rubber band around the five Mbients, tapped
on the table.** 

**Stimulus.** None in code. `clapping_test_obs` is a *recording configuration*
(same 12-device fan-out, `split_task_device_map.yml:276-288`); the "stimulus"
is the operator's physical tap during the recording. There is no clapping task
class — `saccades_sounds.py` and the orphaned `audio_video_test.py` are the
only `test_timing` tasks.

**What it uniquely measures.** Banding the five IMUs together and tapping makes
one physical impact that is genuinely simultaneous across all five
accelerometers *and* produces an audible transient the Yeti records. So the tap
is a shared ground-truth event visible to two independent subsystems. Overlaying
their LSL timestamps (`extras/clapping_test_plotting.py:61` overlays
`Eyelink, Mic, Mbient_RH` plus the three Intel cameras from processed RGB)
exposes: **IMU↔IMU agreement** (do all five spikes land together → G1 within
the Mbient set) and **audio↔IMU offset** (does the mic transient land at the
same LSL time as the accelerometer spike → G1/G2 for the audio path). It is an
audio-vs-IMU synchronization check with the microphone as the device whose
latency is least trusted — hence your "microphone latency" memory.

**How it is run / output.** Same inferred GUI path as Test A.
`extras/clapping_test_plotting.py` carries the same hardcoded `Z:\data` /
`Z:\processed_data` paths and a hardcoded 2022 session id
(`clapping_test_plotting.py:37-39,42`), and again produces a **visual overlay**,
no metrics, no comparator.

**Effort profile.** Lab visit • physical action required (the tap) • no booth
reconfiguration (cameras stay put) • 12-device
production recording • manual post-processing • eyeball output.

### 2.3 Test C — Software clock microbenchmark (latent: `extras/time_clocks*.py`)

**This is the highest value-per-effort test for the OS question and currently has no driver — it just prints.**

`extras/time_clocks.py` times 10 000 repetitions of a 0.5 ms wait implemented
five ways — `pylsl.local_clock` busy-wait, `time.time` busy-wait,
`time.sleep`, `psychopy.core.wait`, and `core.wait(hogCPUperiod=...)` — and
prints five totals. `extras/time_clocks_variance.py` does 100 reps and prints
the per-primitive mean ± SD error vs. the requested interval.

**What it uniquely measures.** The accuracy and variance of the timing
primitives the whole stack is built on. This is a direct probe of the **OS
scheduler and timer resolution** — precisely the layer most likely to change
between Win10 and Win11, and the layer underneath every other timing property.
No devices, no lab, no camera, no subject. It runs headless on a booth in
seconds.

**State.** Orphaned (audit §2.3): no `__main__` driver wiring, no JSON, no
baseline, output is `print()`. Trivially wrappable into a metrics emitter.

### 2.4 Test D — Passive timing from already-collected session data (latent: the `extras/perf/` DB harness)

**This is the highest value overall for regression detection and requires zero lab effort, because the data already exists.**

Every real clinical session already records the timing signal: the LSL marker
stream (`marker.py`), per-device HDF5 with both LSL timestamps and
device-native timestamps, and the `log_sensor_file` / `log_application`
database tables (per-device `file_start_time`/`file_end_time`; timestamped
lifecycle events). The repo already mines this **remotely** through an
SSH-tunnel + Postgres harness:

- `extras/perf/_db.py:28-46` — opens an SSH tunnel to the production DB from
  anywhere with the credentials file and key. This is what makes "remote"
  literally true: it runs from your machine, not the lab.
- `extras/perf/mbient_timing.py` — derives Mbient BLE connect and reset timing
  distributions purely from `log_application`.
- `extras/perf/intertask_report.py` — derives per-device inter-task gap
  statistics from `log_sensor_file`.
- `extras/perf/mbient_timing_before_after.py` — **a direct precedent for an OS
  A/B**: it splits the same metric on a cutover date (`CUTOVER = "2026-03-04"`)
  and prints Before vs. After distributions side by side. Swap "cutover date"
  for "Win10 vs Win11 machine" and the pattern is exactly what #759 needs.

**What it can measure from data we already have**, per device, per session,
trended over time, with no special recording: sampling-interval mean / SD /
p95 / p99, dropped and duplicated frames, LSL-vs-device-native clock drift
(ppm), marker-to-first-sample latency, and cross-device start skew (G1, G3, and
the *variance* component of G4). It cannot see absolute analog latency (G2) —
that requires a physical event of known truth, which production tasks do not
provide. That single gap is the subject of Section 7.

---

## 3. Importance and recommendation, per test

Rated for the **Win10/Win11 regression** purpose specifically (G5), not in the
abstract. "Unique signal" = does anything else give you this number.

| Test | Unique signal | Importance for #759 | Current effort | Remote / automatable today | Recommendation |
|------|---------------|:---:|:---:|:---:|----------------|
| **C — Clock microbenchmark** | Scheduler/timer accuracy & jitter — the root layer | **Critical** | Trivial (orphaned) | Yes, after a thin wrapper | **Make it the backbone.** Wrap to emit JSON; run on every booth, every baseline. |
| **D — Passive session metrics** | Real production-path jitter/drift/drops/skew on real sessions | **Critical** | Low (DB harness exists) | **Yes, fully, today** | **Make it the backbone.** Generalize the before/after pattern to OS A/B. |
| **A — Saccades/sounds (`timing_test_obs`)** | Absolute display + audio → capture latency (G2) — *nothing else gives this* | **Medium (confirmatory)** | Very high (lab + reconfig + multi-GB bag + manual) | No | **Demote to one-time confirmatory** per OS baseline, not per change. Rebuild post-processing into metrics per audit §4. |
| **B — Clapping (`clapping_test_obs`)** | Absolute audio↔IMU offset | **Low** | High (lab + physical action + manual) | No | **Retire as routine.** Its IMU↔IMU and audio-jitter questions are covered by D; its one unique number (absolute mic-vs-IMU offset) can ride along on the single confirmatory run of A. |

Reasoning for the two demotions, stated plainly:

- **Test A is scientifically important but is the wrong cadence.** Absolute
  display/audio latency is a real number you need *once* on a locked Win10
  baseline and *once* on the Win11 pilot to confirm it did not jump. Running it
  on every change is high cost for a quantity that, on unchanged hardware,
  rarely moves (Section 7 argues this physically). Keep it; run it rarely;
  still rebuild its output into numbers (audit §4 steps 1–4) so the one run you
  do produces a comparable artifact rather than a plot read by eye.

- **Test B carries the least unique information for the OS question relative to
  its cost.** IMU-set agreement and audio jitter fall out of Test D from
  ordinary sessions. The only thing B adds over A is an absolute mic-vs-IMU
  offset, and A already exercises the audio path against a known event. If a
  physical run is being done for A anyway, band the Mbients and tap during it;
  that captures B's unique number at zero marginal lab trips. A standalone
  clapping campaign is not justified for #759.

---

## 4. The effort question, scored against the criteria

There are four things to avoid. Scoring each test against them, plus the two
desirable properties  (quantitative output, replicable):

| Criterion (yours) | A: Saccades/sounds | B: Clapping | C: Microbench | D: Passive DB |
|---|:---:|:---:|:---:|:---:|
| (a) Needs booth reconfiguration | **Yes** (repoint camera) | No | No | No |
| (b) Needs physical presence | **Yes** | **Yes** (the tap) | No | No |
| (c) Needs special manual app to analyze | **Yes** (REPL/eyeball) | **Yes** | No (after wrapper) | No |
| (d) Auto-feeds an OS-comparison summary | No (today) | No (today) | Achievable | **Achievable now** |
| Produces quantitative output | No (today) | No (today) | Yes | Yes |
| Practically replicable per run | **No** (undocumented fixture) | **No** | Yes | Yes |

"Practically replicable: No" for A and B is not a guess — `timing_test_recording_audit.md`
§1.4 documents that the recording fixture (duration, scene, lighting, operator
posture, acceptance criteria) is *undefined anywhere*. Two operators on two
OSes cannot currently produce comparable A/B inputs by hand. That is a
reproducibility failure independent of effort.

C and D score clean on every one of your criteria. They are the suite.

### The proposed low-effort suite (reuses three patterns the repo already proves)

Nothing here is novel architecture; each piece mirrors something that already
works in this codebase, which is why it is low-risk:

1. **`extras/perf/timing_baseline.py`** — a metrics emitter modeled
   field-for-field on `extras/perf/win11_readiness.py`. On a booth it:
   - runs Test C (the microbench) and records per-primitive mean/SD/p95/p99;
   - optionally runs Test A's *stimulus alone, single machine, no cameras*
     (`Saccade_synch` already runs standalone) and captures PsychoPy's own
     requested-vs-actual flip-interval statistics and dropped-flip count — this
     yields the **display-timing-jitter** part of G4 with **no camera, no bag
     file, remotely** (it does not yield absolute latency — see §7);
   - emits one JSON to
     `extras/perf/baselines/timing/<os>/<hostname>.json`, using the exact
     envelope `win11_readiness.py:480-499` already uses: `schema_version`,
     `schema_name`, `captured_at`, `machine{hostname,role,os_caption,os_version,os_build}`,
     a `metrics` block, a derived `verdict{category,reasons,remediation_hints}`,
     and `collection_errors`.

2. **`extras/perf/timing_session_metrics.py`** — generalizes the
   `mbient_timing_before_after.py` cutover pattern from "date" to "OS / machine
   set," pulling per-device interval/drift/drop/skew statistics from the DB for
   a date range. Pure `_db.py` SSH-tunnel; runs from your remote machine.

3. **`extras/perf/compare_timing.py`** — ingests two baseline JSONs (Win10
   locked baseline vs Win11 pilot) and emits a delta table with explicit,
   quantitative thresholds (Section 6). This is the "tells me how timing
   changed between OS versions" artifact you asked for.

4. **`docs/timing_summary.md`** — a human roll-up in the exact style of
   `docs/win11_readiness_summary.md`: it points at the authoritative JSONs and
   states "if the doc and the JSON disagree, the JSON wins." The
   change-over-time table format is already demonstrated by
   `docs/perf/inter-task times [2026-04-03].md` (grouped ranges, summary
   mean/median/SD/min/max, per-transition deltas, observations) — that document
   was produced from DB data, remotely, automatically, and is the template for
   what a timing summary should look like.

Pieces 2 and 4 are runnable **today, remotely, with zero lab effort**, against
historical Win10 sessions, to lock the baseline now (Phase 2 of the #759 plan).
Pieces 1 and 3 are small wrappers over code that already exists.

---

## 5. Replicability

Two senses, both of which the suite must satisfy and the physical tests fail:

- **Reproducible (same input → same number).** C is deterministic given a
  machine. D is deterministic given a fixed date range and query. A and B are
  not: per audit §1.4 the fixture is undocumented, and B additionally depends
  on an unstandardized human tap. A normalized matplotlib overlay read by eye
  is not a reproducible measurement.
- **Replicable in practice (cheap to repeat).** C: one command, seconds, no
  hardware. D: one command from your desk, no hardware. A/B: a lab trip, a
  reconfiguration (A), a multi-GB transfer, and manual analysis — repeating
  this every change is exactly the burden you flagged.

The suite makes the *routine loop* fully replicable in both senses. The single
physical confirmatory run (A, once per baseline) is made *reproducible* by the
non-code deliverable the audit already calls out: a written, fixed fixture
(duration / scene / lighting / posture / acceptance criteria). That document is
the one genuinely operator-dependent item and gates the baseline; it is small
but it is not optional, and it cannot be produced from code alone.

---

## 6. Quantitative outputs, with verdict derived *from* the numbers

We want numbers, not pass/fail, but also value flagged concerns. The
established repo pattern already does exactly this and should be copied:
`win11_readiness.py:409-477` keeps the full measured payload *and* derives a
`verdict` with human-readable `reasons[]` from it; the JSON is authoritative,
the verdict is a convenience. Apply the same shape here — emit every number;
derive a verdict so a glance tells you if something moved; never discard the
number behind a boolean.

Metric set (all quantitative, all diffable Win10 vs Win11):

- **Microbench (C):** per-primitive mean, SD, p95, p99, max of the error vs the
  requested interval.
- **Display jitter (A-stimulus-only):** mean/SD of (actual − requested) frame
  interval; dropped-flip count; tone-schedule miss distribution.
- **Per-device, from sessions (D):** sampling-interval mean/SD/p95/p99;
  dropped-frame count and rate; duplicated-sample count; LSL-vs-native clock
  drift in ppm; marker→first-sample latency; cross-device start skew.
- **One-time confirmatory (A/B, per baseline):** absolute display→camera
  latency; absolute audio→sample latency; absolute audio↔IMU offset; IMU↔IMU
  spread.

Proposed starting thresholds for `compare_timing.py` — these are **proposals to
be ratified by whoever owns the timing budget, not measured facts**, and the
raw deltas must be printed regardless of whether a threshold trips:

- jitter SD regression > 25 % vs Win10 baseline → flag;
- any new dropped/duplicated frames where the baseline had effectively none →
  flag;
- clock drift change > a small fixed ppm bound → flag;
- microbench p99 worse by > 2× baseline → flag;
- absolute latency (the rare confirmatory run) moved by more than one frame
  interval / one audio block → flag.

Flag means "a human looks, with the numbers in hand," not "fail."

### 6.1 Where this strategy is weak (read before relying on it)

Three caveats that the rest of this document, if read alone, would understate:

1. **The risk is the metric math, not the plumbing.** The SSH-tunnel DB
   harness, the JSON envelope, and the summary-doc convention are proven repo
   patterns and are genuinely low-risk to reuse. The per-device timing
   *metrics* — native-vs-LSL drift in ppm, dropped/duplicated-frame detection,
   cross-device skew — are **new and unproven here**; the existing perf scripts
   compute coarse durations (connect times, inter-task gaps), not sample-level
   jitter or drift. The inputs are confirmed present every session
   (`camera_intel.py:122-127`, `flir_cam.py:150-153`, `iphone.py:631-635`
   record the device-native clock and frame counter alongside the LSL
   timestamp), so the metrics are *computable* — but a subtly wrong metric
   definition yields confident, wrong A/B deltas, which is the worst failure
   mode here. These definitions need a methodology review before any number is
   trusted; "thin wrapper" describes the plumbing, not the analysis.
2. **C and D are not co-equal and must not be read as one instrument.** The
   microbench (C) is hermetic: it isolates the OS variable cleanly and can be
   run many times for statistical power. The passive session metrics (D) are
   representative of the real production path but, compared across calendar
   time, confound the OS with subjects, room, driver versions, software
   release, and USB/BLE wear — the same weakness the
   `mbient_timing_before_after.py` date-cutover precedent carries. The #759
   clean-pilot plan mitigates this but does not remove it. Treat C as the
   causal instrument and D as the representative corroborator; if they
   disagree, that disagreement is signal, not noise.
3. **"Retire the clapping test" means "fold its tap into the one saccades
   confirmatory run" — an operator action that must actually be scheduled.**
   It is not an automatic consequence. If that folding does not happen, the
   only *direct* absolute audio↔IMU cross-check is lost (the saccades test
   exercises the audio path against a visual event, not against the IMUs).

---

## 7. The honest limit: what cannot be done remotely, and why it is acceptable anyway

You asked to be told if good results are not possible with the kind of tests
you want. Here is the unsoftened answer.

**What the remote suite (C + D + the stimulus-only flip log) gives you:** G1,
G3, the variance part of G4, and a direct read on the most OS-sensitive layer
(G5 via C). For the literal #759 question — *did timing regress between OS
versions* — this is sufficient and is the correct primary instrument. It is
quantitative, replicable, remote, and auto-summarized. This part is a clear
"yes, achievable."

**The one thing it cannot give you:** absolute end-to-end analog latency
(G2) — the fixed millisecond gap between photons leaving the panel and the
camera's sample timestamp, and between the speaker and the mic's sample
timestamp. Measuring that requires an event whose true time is known
independently of the computer, which by definition needs a physical sensor in
the loop. Production data does not contain it; no remote method can recover it.

**Why this is an acceptable limit, not a blocker — three reasons, in order of
weight:**

1. **It is largely OS-insensitive, with one named exception — and the remote
   suite still *detects* that exception even though it cannot *calibrate* it.**
   The audio and IMU/mechanical offsets are genuinely hardware-bound (sound
   card, cable, sensor, driver) and an OS upgrade on the same machine does not
   move them. The **display path is the exception**: Win11's DWM compositor can
   shift the *mean* present latency (e.g. if PsychoPy's present path changes
   between exclusive and composited), so that offset is not purely hardware.
   The rescue is that such a change also leaves a jitter / dropped-flip
   signature, and the stimulus-only flip-interval log (Test A, single machine,
   no camera) captures that signature remotely — so the suite would *flag* a
   Win11 display-path regression. What it cannot do is put an exact millisecond
   number on the offset: the flip log is software-reported and can be
   systematically optimistic about a clean, low-jitter fixed offset. So the
   correct claim is narrower than "least OS-sensitive": *detection of
   display-path change is remote; absolute calibration of the offset is the one
   thing that needs the camera run.* Spending a lab trip every change to
   re-calibrate a number that is hardware-bound for audio/IMU and only
   *detectably* (not precisely) perturbable for display is still poor
   allocation.
2. **It only needs measuring twice.** Once on the locked Win10 baseline, once
   on the Win11 pilot. That is two physical runs total for the whole upgrade
   decision, not two per change. At that cadence the heavyweight test's cost is
   tolerable, and only Test A is needed (it exercises the audio path against a
   known event, so a separate clapping campaign adds little — see §3).
3. **It is the only gap, and it is named and bounded.** Not a fog of "remote
   testing is unreliable" — one specific quantity, measured rarely.

**The only way to make absolute latency cheap and automated** would be a
hardware sync box: a photodiode taped to a screen corner plus an audio loopback,
feeding a known electrical edge into a recorded channel, so display/audio
latency becomes a deterministic number with no camera, no bag file, and no
operator judgement. Be aware this is **net-new hardware that does not exist in
this project today** — a code-wide search finds zero photodiode / trigger-box /
parallel-port references; the camera-films-the-screen method is currently the
*only* way absolute display latency is obtained. A sync box is the right
long-term answer if absolute latency ever needs to be routine, but it is a
procurement plus a one-time physical install, not a software change, and it is
out of scope for getting #759 moving. I am flagging it rather than burying it.

**Net verdict.** Good quantitative results *are* achievable with the kind of
tests you asked for, for the question that matters. Stand up C + D now (both run
remotely against existing data and need only thin wrappers), lock the Win10
baseline from historical sessions immediately (Phase 2), and budget exactly one
physical confirmatory run per OS for the one number that genuinely needs the
lab. The two tests you remembered should not be in the routine loop — not
because timing does not matter, but because the cheap methods cover the part of
timing that actually changes across an OS upgrade, and the expensive methods
should be spent only on the part that does not.

---

## References (all verifiable in-repo)

- `examples/split_task_device_map.yml:276-302` — `clapping_test_obs` /
  `timing_test_obs` 12-device fan-out
- `neurobooth_os/tasks/test_timing/saccades_sounds.py` — Test A stimulus;
  tone-on-flip `:69-70`; markers `:63,72-73,84`; sole entry point `:94-98`
- `neurobooth_os/tasks/test_timing/marker.py:9-31` — marker stream format
- `neurobooth_os/tasks/test_timing/audio_video_test.py` — orphaned task (audit §1.2)
- `extras/clapping_test_plotting.py:37-42,61` — Test B analysis, hardcoded paths
- `extras/plot_timing_test_sync.py:44,54,139-159,166` — Test A analysis,
  hardcoded paths and the two known bugs
- `extras/synch_frame_mean_rgb.py`, `extras/synch_frame_mean_rgb_flir_iphone.py`,
  `extras/convert_bag2vid_timestamps.py` — bag → RGB post-processing chain
- `extras/time_clocks.py`, `extras/time_clocks_variance.py` — Test C, orphaned
- `extras/perf/_db.py:28-46` — remote SSH-tunnel DB access
- `extras/perf/mbient_timing.py`, `extras/perf/intertask_report.py` — Test D
  precedents
- `extras/perf/mbient_timing_before_after.py` — before/after A/B precedent
- `extras/perf/win11_readiness.py:409-499` — metrics-emitter + verdict + JSON
  envelope to copy
- `extras/perf/baselines/win11_readiness/{ctr,stm,acq}.json` — baseline-JSON
  convention
- `docs/win11_readiness_summary.md` — summary-doc convention (JSON authoritative)
- `docs/perf/inter-task times [2026-04-03].md` — change-over-time summary
  format, produced remotely from DB data
- `docs/timing_test_recording_audit.md` — code-state audit; §1.3 inferred
  production path, §1.4 undocumented fixture, §3 gap list, §4 rebuild steps
- Issue #759 (umbrella, concern #3), #761 (timing subtask); Phase 2 = lock
  Win10 baseline, Phase 3 = Win11 pilot diff
