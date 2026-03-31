# System Resource Analysis

Follow-on investigation from the [Inter-Task Gap Analysis](inter_task_gap_analysis.md), examining whether system resource usage explains the session-level variability in inter-task gap duration.

## Data Source

- **Table:** `log_system_resource` — records RAM, swap, CPU (per-core), disk I/O, and network usage every ~10 seconds on each machine
- **Machines:** STM (presentation — runs Eyelink, Mouse), ACQ (acquisition — runs Intel cameras, FLIR, IPhone, Mbients, Mic). ACQ was split into ACQ_0 and ACQ_1 starting Feb 26, 2026.
- **Available from:** Feb 2025 onward (~369K rows)
- **Gap metric:** Per-session Eyelink median inter-task gap (see parent analysis for definition and filters)

## Methodology

For each session, we matched its time window (first task start to last task end) against `log_system_resource` readings on each machine. We then correlated each resource metric with the session's Eyelink median gap using Spearman rank correlation, and compared slow sessions (median gap > 20s) against normal sessions (13–16s) using Mann-Whitney U tests.

## Correlation: Resource Metrics vs Eyelink Gap

| Machine | Metric | Spearman rho | p-value | n |
|:--|:--|--:|--:|--:|
| STM | avg swap MB | **0.221** | **<0.0001** | 548 |
| STM | max swap MB | 0.179 | <0.0001 | 548 |
| STM | avg RAM % | 0.160 | 0.0002 | 548 |
| STM | max RAM % | 0.094 | 0.028 | 548 |
| ACQ | max RAM % | **0.250** | **<0.0001** | 540 |
| ACQ | max swap MB | 0.195 | <0.0001 | 540 |
| ACQ | avg swap MB | 0.123 | 0.004 | 540 |
| ACQ | avg RAM % | -0.083 | 0.055 | 540 |
| ACQ_0 | max swap MB | **0.725** | **0.0003** | 20 |
| ACQ_0 | avg swap MB | 0.594 | 0.006 | 20 |

Swap usage on both STM and ACQ is the most consistently significant metric. The ACQ_0 correlation is very strong (rho=0.725) but based on only 20 sessions (post-split era).

## Slow vs Normal Sessions

### STM machine (runs Eyelink)

| Metric | Slow (>20s, n=54) | Normal (13-16s, n=378) | Mann-Whitney p |
|:--|--:|--:|--:|
| avg swap MB | **65.3** | **30.2** | **0.0001** |
| max swap MB | **178.3** | **125.9** | **0.002** |
| avg RAM % | 23.5 | 22.5 | 0.09 |
| max RAM % | 28.1 | 28.8 | 0.65 |

Slow sessions have **2x the average swap usage** on STM compared to normal sessions. RAM percentage is not significantly different — the memory pressure shows up in swap, not in main RAM.

### ACQ machine (runs cameras)

| Metric | Slow (>20s, n=49) | Normal (13-16s, n=376) | Mann-Whitney p |
|:--|--:|--:|--:|
| max RAM % | **76.3** | **45.9** | **0.0001** |
| max swap MB | **264.3** | **226.5** | **0.0006** |
| avg swap MB | 123.9 | 117.7 | 0.04 |
| avg RAM % | 20.7 | 22.6 | 0.21 |

ACQ shows a different pattern: the **peak RAM** (not average) spikes dramatically on slow sessions (76% vs 46%), suggesting periodic memory pressure bursts rather than sustained high usage. Swap is also elevated but less dramatically than on STM.

## CPU Is Not the Bottleneck

| Machine | Group | Avg CPU | Max core | P95 avg |
|:--|:--|--:|--:|--:|
| STM | Slow | 8.9% | 33.6% | 22.2% |
| STM | Normal | 7.4% | 35.3% | 17.1% |
| ACQ | Slow | 8.7% | 28.6% | 17.7% |
| ACQ | Normal | 14.4% | 45.4% | 29.5% |

CPU utilization is low across the board (< 15% average). Slow sessions actually have *lower* ACQ CPU utilization (8.7% vs 14.4%), likely because devices spend more time blocked on I/O or waiting for orchestration rather than actively processing data.

## Disk I/O Is Slightly Elevated

| Group | STM disk write rate |
|:--|--:|
| Slow | 0.4 MB/s |
| Normal | 0.2 MB/s |

The 2x write rate on slow sessions could be swap-related I/O (pages being written to disk as memory is reclaimed).

## Interpretation

Memory pressure — specifically **swap usage** — is the first system-level factor that clearly differentiates slow from normal sessions. Key observations:

1. **Both machines are affected.** STM shows elevated swap; ACQ shows elevated peak RAM. This explains the earlier finding that slowness is correlated across devices on different machines — both machines experience memory pressure simultaneously.

2. **Consistent with multi-day persistence.** Swap accumulation from processes that don't fully release memory between sessions would produce a slow drift that persists until the machines are rebooted or the offending process is killed. This matches the finding that gap autocorrelation does not decay even at lags of a week.

3. **CPU is ruled out.** The bottleneck is not computational. Devices are waiting, not computing.

## Long-Term Memory Trajectory

We examined daily RAM and swap usage on both machines over a 10-month window (Jun 2025 – Mar 2026). The neurobooth services shut down between sessions, so any memory that persists across sessions must belong to another resident process.

### STM machine

STM RAM grows monotonically across days, only dropping when the machine is rebooted:

| Period | STM avg RAM | Swap avg | Event |
|:--|:--|:--|:--|
| Jun 3–12 | 11 → 18 GB | 0 → 61 MB | Growing |
| Jun 16 | 14 GB | 0 MB | Reset (reboot) |
| Jun 17–26 | 15 → 22 GB | 0 → 53 MB | Growing |
| Jul 1–16 | 20 → 20 GB | 0 → 94 MB | Growing, with spike |
| Aug 13 | 13 GB | 0 MB | Reset |
| Aug 14 – Sep 2 | 13 → 22 GB | 0 → 113 MB | Growing |
| Sep 3 | 10 GB | 0 MB | Reset |
| Sep 4 – Oct 14 | 12 → 23 GB | 0 → 96 MB | Growing |
| Oct 15 | 11 GB | 0 MB | Reset |
| Oct 16 – Nov 11 | 12 → 22 GB | 0 → 64 MB | Growing |
| Nov 12 | 12 GB | 0 MB | Reset |
| Nov 13 – Dec 18 | 13 → 27 GB | 0 → 126 MB | Growing — no reset for 5 weeks |
| **Jan 5** | **12 GB** | **0 MB** | **Reset** |
| **Jan 6–29** | **34 → 37 GB** | **84 → 244 MB** | **Rapid growth, peak RAM/swap** |
| Feb 2 | 14 GB | 0 MB | Reset |
| Feb 3–18 | 15 → 19 GB | 0 → 95 MB | Growing |
| Feb 19 | 12 GB | 0 MB | Reset |
| Feb 24 – Mar 5 | 15 → 19 GB | 0 → 131 MB | Growing |
| Mar 10 | 12 GB | 0 MB | Reset |
| Mar 11–12 | 13 → 14 GB | 0 → 15 MB | Growing (slow day Mar 12: 14 GB + 147 MB swap spike at 19:00) |

**Key pattern:** RAM grows ~1–2 GB per active day. After 3-4 weeks without a reboot, RAM reaches 30+ GB (of 68.5 GB total) and swap climbs to 200-450 MB. The January 2026 period without a reset for ~3 weeks saw STM reach 37-38 GB RAM with 450+ MB swap — coinciding with the slowest measured sessions (v0.55.4/v0.55.5 era, 20-30s gaps).

### ACQ machine (ACQ_0 after Feb 26, 2026)

ACQ shows a similar growth pattern with periodic resets:

- Swap typically runs 60-200 MB, accumulating over days
- On **Nov 20, 2025**, swap spiked catastrophically to **76.8 GB** (max) with RAM hitting 67.5 GB — nearly exhausting all system memory. Swap remained at 600+ MB for the next 4 weeks until a reset on Dec 16.
- Resets are visible as drops in min_swap to 0 MB (e.g., Sep 3, Nov 4, Dec 16, Jan 5, Feb 2, Mar 10)

### Hourly trajectory on the slow day (March 12)

Examining the hourly progression on the anomalously slow day (March 12, median gap 29.5s) vs the normal day before (March 11, 15.5s):

**STM:**

- March 11: swap = 0 MB all day, RAM 12–15 GB
- March 12: swap was 0 MB until 19:00, then jumped to 147 MB and stayed. RAM slightly higher all day (~14 GB vs ~12 GB)

**ACQ_0:**
- March 10: swap starts at 0, climbs to 153 MB by end of day
- March 11: swap at 130–140 MB (carried over — never reset overnight)
- March 12: swap climbs from 103 MB to 196 MB over the day

**ACQ_1 (STM machine running second acquisition service):**
- March 10–11: swap = 0 MB
- March 12: swap jumped to 147 MB at 20:00 simultaneously with STM

The simultaneous swap spike on STM and ACQ_1 (same physical machine) at 19:00–20:00 on March 12 points to a specific event on that machine — possibly a scheduled task, backup, or a shared process allocating a large block of memory.

### Interpretation

A **resident process on each machine is leaking memory** that accumulates across neurobooth sessions and across days. Since the neurobooth services themselves shut down between sessions, this is not a neurobooth code issue — it is an external process.

The growth rate (~1-2 GB/day on STM) and the fact that only machine reboots reset it suggest a persistent background service: Dropbox sync, the Eyelink Host Application, a camera SDK daemon, Windows Defender / antivirus, or a Windows Update agent. The occasional catastrophic spikes (Nov 20 on ACQ: 76.8 GB) suggest a runaway allocation event, not just gradual accumulation.

The direct consequence for session performance: when swap is elevated, device start/stop operations (which involve memory allocation for buffers, file handles, and driver communication) incur page fault latency, adding seconds to each inter-task transition. This affects heavyweight devices (cameras, Eyelink) more than lightweight ones (Mbients, Mic) because they allocate larger buffers.

## Recommendations

1. **Schedule periodic reboots** of both STM and ACQ machines (e.g., weekly overnight) to reset memory accumulation.
2. **Identify the leaking process.** On the next high-swap day, run `tasklist /v` or Process Explorer on each machine to identify which process is consuming the most private bytes.
3. **Monitor swap as a session health metric.** If swap exceeds a threshold (e.g., 200 MB) at session start, flag the session or trigger a preemptive restart.
4. **Investigate the Nov 20 event.** The 76.8 GB swap spike on ACQ suggests a runaway process — check Windows event logs for that date.

## Open Questions

- Which specific process is leaking memory on STM and ACQ?
- Is the Eyelink Host Application left running between sessions?
- Are there scheduled tasks (backups, scans) that coincide with the swap spikes?
- Would restarting only the leaking process (vs full reboot) be sufficient?

## Script

- `extras/resource_analysis.py` — Per-session resource extraction and correlation analysis
