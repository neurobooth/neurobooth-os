# Inter-Task Gap Analysis

## Objective

Understand the variability in time gaps between tasks within sessions. Specifically, identify whether particular devices or task transitions are responsible for unusually long wait times between tasks.

## Data Source

- **Database:** Wang production database (`neurobooth` on `192.168.100.1`, accessed via SSH tunnel through `neurodoor.nmr.mgh.harvard.edu`)
- **Table:** `log_sensor_file` joined with `log_task` and `log_session`
- **Gap definition:** For each device within a session, tasks are ordered by `file_start_time`. The gap is computed as `next_task.file_start_time - current_task.file_end_time` — the idle time on that device between consecutive recordings.

## Data Filters

| Filter | Value | Rationale |
|--------|-------|-----------|
| Study | `study1` | Production study |
| Collection | `mvp_030` | The MVP 30 collection |
| Date | Last 18 months (≥ Sep 2024) | Exclude stale historical data |
| Subject ID | > `100001` | Exclude test subjects |
| Max gap | 15 minutes | Gaps exceeding this are discarded as breaks (physician visits, etc.) |

## Collection Version Change

The mvp_030 collection changed significantly around December 2025:

**Old version (Sep 2024 — Nov 2025, ~677 sessions):** 19 tasks, no breaks or pauses.
```
calibration → pursuit → fixation → gaze_holding → saccades_h → saccades_v →
MOT → DSC → hevelius → passage → ahh → gogogo → lalala → mememe → pataka →
finger_nose → foot_tapping → altern_hand_mov → sit_to_stand
```

**Current version (Dec 2025 — present, ~105 sessions):** 25-28 tasks, with break videos, progress bars, coordinator pauses, and intro segments added. Tasks `gogogo`, `lalala`, `mememe`, and `pataka` were removed. `pursuit`, `MOT`, and `hevelius` were moved to the end.
```
intro_sess → progress_bar_1 → intro_occulo → calibration → pursuit → fixation →
gaze_holding → saccades_h → saccades_v → break_video_1 → progress_bar_2 →
intro_cog → MOT → DSC → hevelius → break_video_2 → progress_bar_3 →
intro_speech → passage → picture_description → ahh → break_video_3 →
coord_pause_1 → finger_nose → foot_tapping → altern_hand_mov → coord_pause_2 →
sit_to_stand
```

**Important implication for analysis:** Many devices (Intel cameras, FLIR, Mbients) do not record during break videos, progress bars, intro segments, or coordinator pauses. When analyzing these devices, the measured "gap" between two consecutive tasks on that device may actually span several hidden tasks. The focused analysis below uses only the current collection version and only considers transitions where both tasks are directly consecutive in the expected order (no hidden tasks in between).

## Device Recording Coverage

Not all devices record during every task. The number of tasks a device sees affects the gaps it reports.

| Device | Tasks recorded | Notes |
|--------|---------------|-------|
| Mic_Yeti_dev_1 | All 28 | Most complete view; sees progress bars, coord pauses |
| Eyelink_1 | ~15 | Sees break videos, intros; misses progress bars, coord pauses |
| FLIR_blackfly_1, Intel_D455_1/2/3 | ~13-14 | Misses breaks, intros, pauses |
| IPhone_dev_1 | ~14 | Similar to Intels |
| Mbient_* | ~12 | Misses breaks, intros, pauses |

## Phase 1: Broad Device Survey

**All devices, all data (filtered as above, both collection versions pooled).**

Devices fall into clear tiers by median inter-task gap:

| Tier | Devices | Median gap |
|------|---------|-----------|
| Fastest | Mbient_*, Mic_Yeti | 6 s |
| Mid | IPhone, FLIR, Intel_D455_1/2/3 | 10–13 s |
| Slowest | Eyelink_1 | 13–18 s |
| Anomalous | Mouse | 155 s (excluded from further analysis) |

Mouse was excluded due to its fundamentally different behavior (likely requires human interaction).

## Phase 2: Transition-Level Analysis (Current Collection)

Using only the current collection (Dec 2025+, ~105 sessions), with the Mic providing the complete task timeline and device-specific gaps computed only for direct transitions (no hidden intermediate tasks).

### Transition gap table (mean ± SD, seconds)

| Pos | Transition | Mic | FLIR | IPhone | D455_1 | D455_2 | D455_3 | Eyelink |
|--:|:--|--:|--:|--:|--:|--:|--:|--:|
| 1 | intro_sess → progress_bar_1 | 5.5±1.0 | — | — | — | — | — | — |
| 2 | progress_bar_1 → intro_occulo | 6.3±0.5 | — | — | — | — | — | — |
| 3 | intro_occulo → calibration | 4.7±0.6 | — | 6.8±0.5 | — | — | — | — |
| 4 | calibration → pursuit | 7.1±1.2 | 9.1±1.3 | 9.2±1.3 | — | — | — | — |
| 5 | pursuit → fixation | 4.4±1.4 | 8.5±1.9 | 8.3±1.5 | 9.5±1.9 | 10.6±2.1 | 11.1±2.2 | 17.5±5.2 |
| 6 | fixation → gaze_holding | 5.6±1.3 | 9.7±1.3 | 9.7±1.4 | 10.5±1.2 | 12.0±1.5 | 12.5±1.6 | 14.9±1.8 |
| 7 | gaze_holding → saccades_h | 5.6±1.6 | 9.7±1.6 | 9.6±1.7 | 10.5±1.4 | 11.8±1.5 | 12.4±1.6 | 14.8±2.0 |
| 8 | saccades_h → saccades_v | 5.9±1.4 | 10.5±2.7 | 10.3±2.0 | 11.3±2.8 | 12.8±3.3 | 13.4±3.4 | 18.8±4.0 |
| 9 | saccades_v → break_video_1 | 5.9±1.4 | 10.4±2.5 | 10.3±2.3 | 11.1±2.5 | 12.5±2.8 | 13.1±2.8 | 19.0±5.9 |
| 10 | break_video_1 → progress_bar_2 | 5.6±1.3 | — | — | — | — | — | — |
| 11 | progress_bar_2 → intro_cog | 6.3±0.6 | — | — | — | — | — | — |
| 12 | intro_cog → MOT | 6.6±2.0 | — | 8.7±2.2 | — | — | — | 15.8±2.7 |
| 13 | MOT → DSC | 6.9±29.5 | 22.0±36.3 | 21.8±36.4 | 23.5±36.1 | 25.1±36.2 | 25.7±36.2 | 32.2±36.4 |
| 14 | DSC → hevelius | 13.0±64.0 | 20.9±65.1 | 20.8±65.5 | 22.3±65.0 | 24.0±64.9 | 24.6±64.9 | 27.0±65.1 |
| 15 | hevelius → break_video_2 | 4.3±1.6 | 13.2±10.7 | 13.0±10.6 | 14.5±11.2 | 16.5±11.5 | 17.1±11.5 | 19.6±11.5 |
| 16 | break_video_2 → progress_bar_3 | 5.3±1.3 | — | — | — | — | — | — |
| 17 | progress_bar_3 → intro_speech | 6.3±0.6 | — | — | — | — | — | — |
| 18 | intro_speech → passage | 5.0±0.7 | — | 7.3±0.8 | — | — | — | 13.8±2.7 |
| 19 | passage → picture_description | 5.6±1.6 | 10.0±2.2 | 9.7±2.2 | 11.0±2.2 | 12.5±2.3 | 13.1±2.3 | 16.7±2.7 |
| 20 | picture_description → ahh | 5.9±1.4 | 11.8±7.9 | 10.8±3.2 | 12.6±8.5 | 14.2±8.6 | 14.8±8.7 | 17.1±8.9 |
| 21 | ahh → break_video_3 | 5.6±1.5 | 10.1±2.7 | 9.9±2.5 | 11.2±2.9 | 12.7±3.1 | 13.2±3.1 | 15.5±3.4 |
| 22 | break_video_3 → coord_pause_1 | 11.1±55.6 | — | — | — | — | — | — |
| 23 | coord_pause_1 → finger_nose | 5.9±1.3 | — | — | — | — | — | — |
| 24 | finger_nose → foot_tapping | 5.8±1.4 | 12.4±10.5 | — | 13.8±15.5 | 15.3±16.4 | 15.8±16.5 | — |
| 25 | foot_tapping → altern_hand_mov | 6.0±1.3 | 10.2±2.0 | — | 10.6±2.0 | 11.8±2.4 | 12.3±2.3 | — |
| 26 | altern_hand_mov → coord_pause_2 | 5.6±1.1 | — | — | — | — | — | — |
| 27 | coord_pause_2 → sit_to_stand | 6.1±1.1 | — | — | — | — | — | — |

"—" indicates the device does not record both tasks in the transition (gap not measurable as a direct transition).

### Consistent device overhead

Across nearly all transitions, devices add a consistent offset above the Mic baseline:

| Device | Typical overhead above Mic |
|--------|---------------------------|
| FLIR_blackfly_1 | +4–5 s |
| IPhone_dev_1 | +4–5 s |
| Intel_D455_1 | +5–6 s |
| Intel_D455_2 | +6–7 s |
| Intel_D455_3 | +7–8 s |
| Eyelink_1 | +10–13 s |

### High-variance transitions

Two transitions have anomalously high standard deviations (~36s and ~65s) across all devices:

- **MOT → DSC** (position 13): SD ~36s on every device
- **DSC → hevelius** (position 14): SD ~65s on every device

## Phase 3: Long-Pole Device Identification

For the two high-variance transitions, **Eyelink_1 is the long pole:**

**MOT → DSC:**
- Eyelink has the largest gap in 110/110 sessions (100%)
- Eyelink is always the last device to start DSC
- In the 5 sessions where the gap exceeded 60s, Eyelink was the bottleneck in all 5

**DSC → hevelius:**
- Eyelink has the largest gap in 102/103 sessions (99%)
- In the 3 sessions with gap > 60s, Eyelink was the bottleneck in 2

### Does MOT task duration predict the MOT→DSC gap?

We tested whether longer MOT recordings (which vary by subject performance) lead to longer subsequent gaps — e.g., the Eyelink needing more time to flush a larger data file.

**Spearman rho = 0.498 (p < 10^-46)** — a moderate rank correlation. The trend in medians is clear:

| MOT duration | N | Median gap | Mean gap |
|:--|--:|--:|--:|
| < 5 min | 35 | 19.0s | 29.4s |
| 5–7 min | 361 | 21.0s | 25.9s |
| 7–9 min | 261 | 23.0s | 28.8s |
| 9–12 min | 55 | 26.0s | 34.9s |
| 12+ min | 15 | 30.0s | 86.9s |

However, the **extreme outliers (gap > 60s) are not explained by MOT duration.** Sessions with gap > 60s (n=29) had a median MOT duration of 418s vs 408s for sessions with gap <= 30s (n=657) — not significantly different (Mann-Whitney p=0.12). The worst gaps (335–759s) occur across a wide range of MOT durations (206s to 865s).

**Two distinct effects:**
1. **Gradual trend:** Longer MOT tasks add a few seconds to the subsequent gap (19s → 30s median across the duration range), likely from the Eyelink needing more time to close a larger recording file.
2. **Extreme blowups (60s+):** Independent of MOT duration — driven by the systemic session-level slowness identified in subsequent phases.

## Phase 4: Session-Level Correlation Analysis

### Is MOT→DSC a trigger or a symptom?

We tested whether a slow MOT→DSC gap predicts slow subsequent transitions. Using Spearman rank correlation between the Eyelink's MOT→DSC gap and every other Eyelink transition gap within the same session:

| Transition | Spearman rho | p-value | Relative to MOT→DSC |
|:--|--:|--:|:--|
| pursuit → fixation | 0.464 | <0.0001 | Before |
| fixation → gaze_holding | 0.411 | <0.0001 | Before |
| gaze_holding → saccades_h | 0.448 | <0.0001 | Before |
| saccades_h → saccades_v | 0.571 | <0.0001 | Before |
| saccades_v → break_video_1 | 0.575 | <0.0001 | Before |
| break_video_1 → intro_cog | 0.384 | <0.0001 | Before |
| intro_cog → MOT | 0.482 | <0.0001 | Before |
| **MOT → DSC** | **1.000** | — | **Trigger** |
| DSC → hevelius | 0.532 | <0.0001 | After |
| hevelius → break_video_2 | 0.742 | <0.0001 | After |
| break_video_2 → intro_speech | 0.402 | <0.0001 | After |
| intro_speech → passage | 0.399 | <0.0001 | After |
| passage → picture_description | 0.469 | <0.0001 | After |
| picture_description → ahh | 0.523 | <0.0001 | After |
| ahh → break_video_3 | 0.541 | <0.0001 | After |

**Finding:** Upstream transitions are equally correlated with MOT→DSC as downstream transitions. This means MOT→DSC is not a trigger that causes subsequent delays — it is a symptom of a session-wide Eyelink performance issue. Sessions where the Eyelink is slow are slow from the very first transition through the last.

### Is the slowness machine-specific or system-wide?

We correlated per-session median gap between the Eyelink and every other device. From the staging config, Eyelink runs on the **STM (presentation) machine** while most cameras run on the **ACQ (acquisition) machine**.

| Device | Machine | Spearman rho | p-value |
|:--|:--|--:|--:|
| Intel_D455_2 | ACQ | 0.744 | <0.0001 |
| Intel_D455_3 | ACQ | 0.735 | <0.0001 |
| Intel_D455_1 | ACQ | 0.717 | <0.0001 |
| FLIR_blackfly_1 | ACQ | 0.481 | <0.0001 |
| IPhone_dev_1 | ACQ | 0.454 | <0.0001 |
| Mouse | STM | 0.202 | 0.03 |
| Mbient_BK_1 | ACQ | 0.196 | 0.03 |
| Mbient_LH_2 | ACQ | 0.150 | 0.10 |
| Mbient_RH_2 | STM | 0.130 | 0.16 |
| Mic_Yeti_dev_1 | ACQ | 0.063 | 0.49 |
| Mbient_RF_2 | STM | 0.006 | 0.95 |
| Mbient_LF_2 | STM | 0.007 | 0.94 |

**Finding:** The session-level slowness is **not machine-specific**. The Intel cameras (ACQ machine) are the most correlated with Eyelink (STM machine) at rho ~0.72–0.74. Meanwhile, Mouse (same STM machine as Eyelink) shows almost no correlation. Mbients and Mic are uncorrelated regardless of machine.

This suggests the slowness affects the **system-wide orchestration layer** (database messaging, task sequencing coordination) rather than any single machine. Devices with heavier start/stop overhead (cameras, Eyelink) are more sensitive to this systemic latency, while lightweight devices (Mbients, Mic) are unaffected.

## Phase 5: Cross-Session Persistence

We examined whether the slowness persists across sessions — does a slow session predict that the next session (or sessions days later) will also be slow?

### Within-day consistency

Sessions on the same day have nearly identical gap behavior. The median within-day coefficient of variation (CV) across days with 3+ sessions is **0.066** — essentially no variation within a day.

Examples:
| Date | Sessions | Median gaps (s) | CV |
|:--|--:|:--|--:|
| 2025-12-11 | 4 | 15, 16, 16, 16 | 0.03 |
| 2026-01-20 | 4 | 18, 18, 18, 18 | 0.02 |
| 2026-02-05 | 5 | 20, 19, 20, 20, 19 | 0.03 |
| 2026-03-12 | 4 | 28, 30, 31, 29 | 0.04 |

2026-03-12 stands out as a uniformly slow day (~2x the typical 15s baseline).

### Autocorrelation across sessions

We computed Spearman rank correlation between each session's Eyelink median gap and that of sessions at increasing lags (ordered chronologically):

| Lag | Median time apart | Spearman rho | p-value |
|--:|:--|--:|--:|
| 1 | < 1 min | 0.542 | <0.0001 |
| 2 | < 1 min | 0.496 | <0.0001 |
| 3 | < 1 min | 0.468 | <0.0001 |
| 5 | < 1 min | 0.463 | <0.0001 |
| 8 | < 1 min | 0.505 | <0.0001 |
| 12 | 1.4 days | 0.473 | <0.0001 |
| 15 | 6.7 days | 0.501 | <0.0001 |

The autocorrelation **does not decay** — rho stays in the 0.45–0.54 range from minutes apart to nearly a week apart.

### Correlation by time gap between consecutive sessions

| Time apart | n pairs | Spearman rho | p-value |
|:--|--:|--:|--:|
| < 30 min | 677 | 0.492 | <0.0001 |
| 1–2 hrs | 15 | 0.651 | 0.009 |
| 4–24 hrs | 25 | 0.471 | 0.018 |
| 3–7 days | 13 | 0.749 | 0.003 |
| 7+ days | 25 | 0.554 | 0.004 |

The 3–7 day bucket has the **strongest** correlation (rho=0.75). The correlation at 7+ days (rho=0.55) is still highly significant.

### Interpretation

The slowness is **semi-permanent**. It is not caused by transient factors like CPU load, memory pressure, or network congestion — those would produce short-lived effects that decay within hours. Instead, the persistence across days and weeks points to a structural or environmental factor that changes infrequently: a software version, a configuration setting, a background process, or a hardware state (e.g., Eyelink firmware/calibration profile).

## Phase 6: Investigating Potential Causes

We tested several hypotheses for what drives the day-to-day variance in gap duration. All were negative.

### System resources (RAM, CPU)

We compared STM and ACQ machine RAM and CPU usage on slow days (day median > 20s) vs normal days. RAM utilization was low on all days (18–25% typical, with one day at 54% on STM that showed no gap difference from an adjacent day at the same level). **STM average RAM vs Eyelink gap: rho=-0.086, p=0.57.** No relationship.

CPU usage data was available but showed no differentiation between slow and normal days.

### Application errors and warnings

Error and warning counts from `log_application` were compared on slow vs normal days. Counts were similar (5–11 errors/day on both slow and normal days). No Eyelink-specific errors were found on any slow day. The types of errors (FLIR setting errors, Mbient disconnects, RealSense timeouts) were not correlated with gap behavior.

### Software version

Application versions are tracked in `log_session` starting from v0.55.4 (Jan 2026). A version-level analysis initially appeared to show that v0.59.0 and v0.59.1 were faster (median 15.5–16s vs 18–20s for other versions), but these versions had only **2 sessions each** — far too few to draw conclusions. All versions with adequate sample size (n≥7) showed medians in the 18–24s range. The same version (v0.62.1) produced 15.5s on one day and 31s the next. **Software version does not explain the variance.**

A notable step change occurred in Dec 2024: median gaps jumped from ~10s (Sep–Nov 2024, old collection) to ~14–15s (Dec 2024+). The cause of this shift is unknown — no version tracking existed in that period.

### Time of day

Hour of day vs median gap: Spearman rho=0.096 (p=0.007). Statistically significant but practically meaningless — explains ~1% of variance.

| Hour | N | Median gap |
|--:|--:|--:|
| 7h | 10 | 10.2s |
| 9h | 67 | 12.0s |
| 12h | 83 | 15.0s |
| 13h | 74 | 17.0s |
| 16h | 50 | 18.2s |
| 17h | 128 | 15.0s |

The 7am and 9am sessions appear faster, but these are confounded with the old collection era (which had lower gaps overall). **Time of day does not explain the variance.**

### Position within day

We tested whether the first session of the day differs from later sessions, and whether gaps increase over the course of a day.

- Within-day session order vs gap: rho=0.045, p=0.26
- Hours since first session vs gap: rho=0.024, p=0.56
- First session (median=15.0s) vs later sessions (median=15.0s): Mann-Whitney p=0.17

**No effect of session position within the day.**

### Number of sessions per day

We tested whether high-volume days (many sessions) produce slower gaps, using the **day-level median** to avoid the sampling artifact of more sessions being more likely to contain outliers.

| Sessions/day | N days | Median of day medians |
|--:|--:|--:|
| 1 | 56 | 14.5s |
| 2 | 57 | 15.0s |
| 3 | 50 | 15.0s |
| 4 | 39 | 15.0s |
| 5 | 30 | 15.0s |
| 6 | 17 | 15.0s |
| 7 | 7 | 15.0s |

No pairwise comparison was significant (all p > 0.22). **Session volume does not stress the system.**

### Factors not yet tested

- Staff ID (operator effect)
- Network conditions between machines
- Eyelink calibration quality or mode

## Summary of Findings

1. **Device overhead is consistent and additive.** Each device adds a fixed amount of time to every transition: Mic ~5s, cameras ~10–13s, Eyelink ~15–19s. This is stable across transitions and sessions.

2. **Eyelink_1 is the slowest device** at every transition, adding 10–13s over the Mic baseline.

3. **Two transitions (MOT→DSC, DSC→hevelius) have high variance** driven by occasional extreme delays. Eyelink is the bottleneck in nearly 100% of these cases.

4. **Session-level slowness is systemic, not device-specific.** Slow sessions are slow across all heavy devices (cameras + Eyelink) regardless of which physical machine they run on. Lightweight devices (Mbients, Mic) are unaffected.

5. **The slowness is a session-level trait, not a cascading failure.** Slow sessions are slow from the first transition onward — there is no specific task or event that triggers the degradation.

6. **The slowness persists across days and weeks.** Within-day sessions are nearly identical (CV ~0.07). Cross-session autocorrelation does not decay even at lags of a week (rho ~0.50). This rules out transient causes and points to a semi-permanent environmental or configuration factor.

7. **Memory pressure (swap) is the strongest correlate found.** See [System Resource Analysis](system_resource_analysis.md) for details.

## Scripts

- `extras/analyze_inter_task_gaps.py` — Broad device survey with gap distributions
- `extras/analyze_high_gap_devices.py` — Focused analysis of high-gap devices by task and position
- `extras/resource_analysis.py` — System resource correlation analysis
- Output saved in `extras/gap_analysis_output/` and `extras/high_gap_output_filtered/`
