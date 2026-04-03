# Mbient Connection Times — 2026-04-03

## Setup

Five mbient wearables across two machines:

| Machine | Devices | Service (before Mar 4) | Service (after Mar 4) |
|---------|---------|------------------------|----------------------|
| ACQ | RH, LH, BK | ACQ_0 | ACQ_0 |
| STM | RF, LF | STM (presentation) | ACQ_1 (acquisition) |

Cutover date: **March 4, 2026** (configs v0.61.0 — "Move Mouse and foot Mbients to new ACQ_1 service"). RF/LF remain on the STM machine; only the managing service changed.

Data source: `log_application` table, neurobooth database. Sep 20, 2025 – Apr 2, 2026 (282 sessions).

Note: `log_application.server_type` still logs RF/LF as `presentation` because `PostgreSQLHandler` derives the value from `USERPROFILE`, not the actual service identity. See [#643](https://github.com/neurobooth/neurobooth-os/issues/643). All breakouts in this document use `server_id` (machine hostname) to avoid conflating the two acquisition services.

## 1. Connect Devices (Initial Connection)

Measured as BLE Scan to last Starting Streaming per machine per session. Includes the full per-device cycle: BLE scan (fixed 10s), connect, identify model, reset, reconnect, setup, start streaming.

### Total by machine

| Machine | Devices | Mean | Median | p75 | Max | N |
|---------|---------|-----:|-------:|----:|----:|--:|
| ACQ [RH, LH, BK] | ACQ_0 | 70.2s | 39.8s | 62.7s | 298.0s | 281 |
| STM [RF, LF] | STM/ACQ_1 | 61.9s | 30.6s | 48.0s | 269.0s | 55 |
| **Total (wall-clock)** | | **70.3s** | **40.1s** | **62.6s** | **298.0s** | **282** |

STM has fewer data points because `prepare_scan` was not consistently logged by the presentation service.

### Per device

| Device | Machine | Mean | Median | p75 | Max | N |
|--------|---------|-----:|-------:|----:|----:|--:|
| RH | ACQ | 25.2s | 18.0s | 26.0s | 271.9s | 274 |
| LH | ACQ | 22.1s | 17.4s | 24.2s | 268.1s | 274 |
| BK | ACQ | 24.8s | 17.6s | 25.0s | 266.1s | 270 |
| RF | STM | 8.8s | 6.2s | 10.6s | 117.1s | 226 |
| LF | STM | 9.3s | 6.9s | 12.1s | 119.7s | 230 |

### Before/after ACQ_1 cutover (March 4)

| Machine | Service | Before (median) | After (median) | N before | N after |
|---------|---------|---:|---:|---:|---:|
| ACQ [RH, LH, BK] | ACQ_0 | 39.6s | 42.4s | 226 | 55 |
| STM [RF, LF] | STM / ACQ_1 | 50.7s | 29.2s | 1 | 54 |
| **Total wall-clock** | | **39.7s** | **44.3s** | **227** | **55** |

The STM "before" has only 1 data point (BLE scan rarely logged by the old presentation service). The ACQ machine is the long pole in both periods, so total wall-clock is essentially unchanged.

## 2. Mbient-Reset Pause (Mid-Session)

Measured as `reset_and_reconnect: Resetting` to `Reset Completed` during coord_pause tasks. No camera initialization happens during this phase — only mbients are reconnecting.

### Per device

| Device | Machine | Mean | Median | p75 | Max | N |
|--------|---------|-----:|-------:|----:|----:|--:|
| RH | ACQ | 16.4s | 11.1s | 18.2s | 298.7s | 220 |
| LH | ACQ | 13.3s | 9.3s | 17.1s | 74.0s | 227 |
| BK | ACQ | 13.2s | 8.9s | 17.6s | 75.3s | 220 |
| RF | STM | 6.8s | 5.1s | 8.0s | 30.6s | 226 |
| LF | STM | 8.3s | 5.8s | 10.1s | 114.3s | 228 |

### Per machine (wall-clock, max across devices)

| Machine | Mean | Median | p75 | Max | N |
|---------|-----:|-------:|----:|----:|--:|
| ACQ [RH, LH, BK] | 25.0s | 19.3s | 28.9s | 298.7s | 215 |
| STM [RF, LF] | 10.5s | 8.5s | 12.2s | 114.3s | 216 |
| **Total wall-clock** | **26.0s** | **19.8s** | **29.0s** | **298.7s** | **217** |

### Before/after ACQ_1 cutover

**Per device:**

| Device | Machine | Before (median) | After (median) |
|--------|---------|---:|---:|
| RH | ACQ | 11.0s | 11.8s |
| LH | ACQ | 10.6s | 6.0s |
| BK | ACQ | 8.8s | 8.9s |
| **RF** | **STM** | **5.1s** | **5.4s** |
| **LF** | **STM** | **5.8s** | **5.5s** |

**Per machine:**

| Machine | Before (median) | After (median) |
|---------|---:|---:|
| ACQ [RH, LH, BK] | 19.1s | 19.8s |
| STM [RF, LF] | 8.5s | 8.0s |
| Total wall-clock | 20.1s | 19.8s |

Moving RF/LF from the STM presentation service to ACQ_1 had no measurable impact on reset timing. RF/LF times (5–6s median) were already fast and stayed the same. The ACQ machine remains the bottleneck.

## 3. Initial Connect vs Reset: Code Path Differences

The two phases do not execute the same amount of BLE work per device.

**Initial connect** (`connect()`, `mbient.py:664`):
1. `prepare_scan()` — BLE scan (fixed 10s, once per machine, not per device)
2. `_ble_connect()` — first BLE connection
3. Model/wrapper identification
4. `reset()` — board reset (forces disconnect)
5. `sleep(retry_delay_sec)` — deliberate pause before reconnect
6. `_ble_connect()` — second BLE connection
7. `_create_outlet()` — create LSL stream
8. `setup()` — configure sensors and data callback
9. Post `DeviceInitialization` to CTR

**Mid-session reset** (`reset_and_reconnect()`, `mbient.py:632`):
1. `stop()` — stop streaming
2. `reset()` — board reset (forces disconnect)
3. `_ble_connect()` — BLE connection
4. `setup()` — configure sensors and data callback
5. `start()` — resume streaming

The shared core is reset → BLE connect → setup. Initial connect adds a BLE scan (per machine), an extra BLE connection, model identification, a sleep, and LSL outlet creation. This means per-device initial connect times include **two** BLE connections while reset includes **one**.

This is important context for interpreting the ACQ vs STM comparison below: the raw times differ between phases partly because of this workload difference. However, the **ACQ/STM ratio** is the right metric for isolating machine-level effects, because both machines execute the same code path in each phase.

## 4. Why Is ACQ Slower?

ACQ devices are individually ~3x slower than STM devices during initial connect, and ~2x slower during mid-session reset. Two factors contribute.

### 4a. Machine load during initial connect

ACQ initializes 9 devices concurrently (3 Intel D455 cameras, FLIR, iPhone, Mic, 3 Mbients). STM initializes 4 (Eyelink, Mouse, 2 Mbients). Camera initialization overlaps with BLE connections and measurably slows the BLE stack.

| Phase | ACQ per-device (median) | STM per-device (median) | ACQ/STM |
|-------|---:|---:|---:|
| Initial connect (cameras starting) | 17.6s | 6.4s | **2.7x** |
| Mid-session reset (cameras idle) | 9.4s | 5.5s | **1.7x** |

The ACQ/STM ratio widens from 1.7x to 2.7x when cameras are initializing. Both machines execute the same code path in each phase (see Section 3), so the extra work in initial connect affects both equally. If the slowdown were purely from more BLE operations, the ratio would stay at 1.7x. The widening to 2.7x indicates that camera/USB/CPU contention on ACQ is adding a per-BLE-operation penalty that STM does not experience.

### 4b. Baseline hardware/RF penalty

Even during mid-session reset — when no other devices are initializing — ACQ devices are 1.7x slower than STM. This persistent gap points to differences between the two machines that are not related to software load: Bluetooth adapter hardware, drivers, RF environment, or physical distance to the wearables.

### 4c. Parallelism and tail latency

ACQ devices connect with ~51% overlap (vs 67% theoretical max for 3 parallel devices). The last device to finish is heavily penalized:

| Finish order | Median connect time | Most common device |
|---|---:|---|
| 1st | 11.1s | BK (101), RH (93), LH (87) |
| 2nd | 18.4s | LH (108), RH (86), BK (83) |
| 3rd | 26.7s | RH (95), BK (86), LH (79) |

No single device is consistently last — all three rotate — confirming this is contention (BLE radio or system resources), not a faulty device.

### 4d. BLE scan

The BLE scan is a fixed 10s on both machines and is not a differentiator.

## 5. Time-Period Trends

### Connect devices by machine

| Period | ACQ median | STM median |
|--------|---:|---:|
| 6-mo baseline (Sep 20 – Mar 20) | 39.4s | 31.0s |
| Mar 24–26 | 57.4s | 23.9s |
| Mar 30–31 | 115.3s | 111.3s |
| Apr 1–2 | 39.5s | 22.2s |

### Reset pause by machine (per device)

| Period | ACQ median | STM median |
|--------|---:|---:|
| 6-mo baseline | 9.8s | 5.6s |
| Mar 24–26 | 6.3s | 4.9s |
| Mar 30–31 | 15.7s | 5.9s |
| Apr 1–2 | 5.5s | 4.6s |

## Appendix: Device Inventory per Machine

**ACQ** (9 devices): FLIR_blackfly_1, Intel_D455_1, Intel_D455_2, Intel_D455_3, IPhone_dev_1, Mic_Yeti_dev_1, Mbient_RH_2, Mbient_LH_2, Mbient_BK_1

**STM** (4 devices): Eyelink_1, Mouse, Mbient_RF_2, Mbient_LF_2

## Scripts

Analysis scripts in `extras/`:
- `mbient_timing.py` — overall connect and reset timing with time-period breakdown
- `mbient_timing_before_after.py` — before/after ACQ_1 cutover comparison
- `mbient_acq_bottleneck.py` — ACQ vs STM per-device, sequencing, and load analysis
