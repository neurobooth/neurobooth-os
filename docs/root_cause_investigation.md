# Root Cause Investigation: Inter-Task Gap Slowdowns

Follow-on investigation from the [Inter-Task Gap Analysis](inter_task_gap_analysis.md) and [System Resource Analysis](system_resource_analysis.md), exploring specific causes of the session-level slowdowns.

## Context

The system resource analysis identified two mechanisms driving slow sessions:
1. **ACQ machine:** Task-driven RAM spikes (up to 51 GB on slow sessions vs 31 GB normal) force swapping. Pages evicted during spikes must be faulted back in during transitions.
2. **STM machine:** Gradual background memory accumulation (growing ~1-2 GB/day until reboot) raises baseline swap usage.

This document investigates the specific processes and behaviors behind these patterns.

## ACQ RAM Spike Analysis

Slow sessions on ACQ show dramatically different RAM dynamics than normal sessions:

| Metric | Slow (>20s, n=54) | Normal (13-16s, n=378) | p-value |
|:--|--:|--:|--:|
| RAM max (GB) | **51.1** | **31.4** | 0.002 |
| RAM range (GB) | **39.5** | **22.6** | 0.001 |
| RAM min (GB) | 7.3 | 10.1 | 0.003 |
| RAM std (GB) | 3.4 | 2.7 | 0.001 |

The pattern: slow ACQ sessions have huge RAM swings — spiking to 51 GB during tasks then dropping to 7 GB between tasks. This 44 GB range forces Windows to swap aggressively during peak usage. When the next task starts and needs those pages back, they must be faulted in from the page file.

ACQ RAM max (rho=0.225, p<0.0001) and RAM range (rho=0.241, p<0.0001) are both significantly correlated with gap duration.

### Key question: What causes the ACQ RAM spikes?

The ACQ machine runs: Intel_D455_1/2/3 (depth cameras), FLIR_blackfly_1, IPhone_dev_1, Mbient_BK_1/LH_2/RH_2, and Mic_Yeti_dev_1 (in the pre-split era; post-split some devices moved to ACQ_1).

Devices that allocate large buffers during recording (camera frame buffers, depth streams) are the most likely source.

## FLIR Queue Investigation

### Architecture

The FLIR camera pipeline (`flir_cam.py`) works as follows:

1. **Capture thread** (`record()`) captures frames from the Spinnaker SDK and puts them on `self.image_queue` — a `queue.Queue(0)` (unbounded).
2. **Save thread** (`camCaptureVid()`) reads from the queue, compresses each frame via OpenCV `video_out.write()`, and writes to disk. This runs as a separate Python thread (GIL-limited).
3. **Queue monitoring:** Every 1000 frames captured, if the queue has > 2 frames, a debug message is logged: `"Queue length is {N} frame count: {M}"` (from `flir_cam.py`, logged via `log_application` with `filename='flir_cam.py'`).

### Does the save thread run during the next task?

**No — `stop_cameras()` blocks until the queue is fully drained.** The shutdown sequence is:

1. `stop_cameras()` calls `stream.stop()` on each camera, which sets `self.recording = False`.
2. Then calls `stream.ensure_stopped(10)`, which calls `self.video_thread.join()` — **blocking indefinitely** until the thread exits (the timeout parameter is ignored in the implementation).
3. The save thread's loop condition is `while self.recording or self.image_queue.qsize()` — so it continues draining the queue after `recording` is set to `False`, then exits.
4. Only after `ensure_stopped()` returns does `server_acq.py` post the `RecordingStopped` message.

So the FLIR queue IS fully drained between tasks. However, the time spent draining **is part of the inter-task gap** — if the queue is large, `ensure_stopped()` blocks for a long time, delaying the `RecordingStopped` message.

Note: Unlike the Intel camera, FLIR's `start()` does not check whether a previous thread is still alive. If `ensure_stopped()` were to be skipped or time out, there would be a race condition. Currently this is not a problem since `join()` blocks indefinitely.

### Correlation with slow sessions

Using the correct log pattern (`filename = 'flir_cam.py' AND message LIKE 'Queue%'`), we found **28,026 queue messages** across the 18-month window — far more than initially thought.

**Day-level correlation with Eyelink gap:**

| Metric | Spearman rho | p-value |
|:--|--:|--:|
| Queue message count | 0.526 | <0.0001 |
| Max queue length | 0.558 | <0.0001 |
| Mean queue length | 0.546 | <0.0001 |

This is a moderate-strong correlation — stronger than any system resource metric except ACQ_0 swap (which had n=20).

**However, the relationship is not causal.** The worst FLIR queue days are NOT the slowest days, and the slowest days often have minimal queue activity:

Top 3 FLIR queue days (1000+ messages, max queue 25K-31K frames): all had **normal** gap times (16-17s).

Top 3 slowest days: Oct 14 (62.5s, 11 queue msgs), May 5 (33.5s, 9 msgs), Sep 19 (33.5s, 204 msgs).

**Slow vs normal days:**

| Metric | Slow days (>20s, n=13) | Normal days (13-16s, n=166) | Mann-Whitney p |
|:--|--:|--:|--:|
| Queue messages | 142 | 33 | 0.07 |
| Max queue length | 4,060 | 179 | 0.10 |
| % days with any queue events | 100% | 95% | — |

Not statistically significant at p<0.05. The FLIR queue falling behind appears to be another **symptom** of the same underlying system pressure, not a cause: when the system is under memory/swap pressure, both the FLIR compression thread slows down AND inter-task transitions are slow.

### How memory pressure causes the FLIR save thread to fall behind

The save thread's hot loop is: `image_queue.get()` → `video_out.write(frame)`. Under memory pressure, several factors slow this down:

1. **Page faults on queue reads.** If the system has swapped out older frames in the queue (which Windows does proactively for "inactive" pages), each `image_queue.get()` must page the frame data back in from disk. At ~1-5 MB per frame and 0.1-0.5ms per page fault, accessing a swapped-out frame adds milliseconds.

2. **Compression buffer allocation.** OpenCV's `video_out.write()` allocates temporary buffers for compression. Under memory pressure, these allocations may trigger page evictions of other data, causing cascading faults.

3. **GIL contention under pressure.** The save thread must acquire the GIL for every Python operation. When the main thread is also active (capturing frames, managing LSL streams), the save thread gets less GIL time. Under memory pressure, GIL acquisitions themselves take longer because the thread scheduler is doing more work.

4. **Disk I/O competition.** If the system is actively swapping (reading/writing pages to the page file), the SSD is shared between swap I/O and the FLIR's video writes, reducing effective write bandwidth.

The net effect: the save thread that normally keeps up at 30fps starts falling behind by fractions of a frame per second, and over a 7-minute task, this accumulates into thousands of queued frames.

### Architecture risks

1. **Unbounded queue** — no cap on memory growth. A bounded queue with a drop-oldest or block policy would prevent runaway memory accumulation.
2. **Python threading (GIL-limited)** — the compression thread competes with the main thread for the GIL. Under load, compression throughput degrades.
3. **`ensure_stopped()` blocks indefinitely** — the timeout parameter is ignored. A very large queue backlog (e.g., 96,905 frames on Nov 20, 2025) could block for minutes.
4. **Process isolation** — rather than moving the compression to a subprocess within the FLIR code, a cleaner fix is to move the Intel cameras (the heavier devices) to their own acquisition process, reducing GIL and memory pressure on the FLIR. See the "Recommendation: Split ACQ_0" section below.

## MOT Duration → Gap Correlation Revisited

The earlier finding that MOT task duration correlates with MOT→DSC gap (Spearman rho=0.498) may be partially explained by the FLIR queue: longer tasks give the queue more time to accumulate frames if compression falls behind. However, since the FLIR queue rarely falls behind, this correlation likely reflects a different mechanism — possibly the Eyelink needing more time to close a larger recording file, or general memory pressure from longer recordings across all devices.

## CPU and GIL Analysis

We investigated whether Python's GIL (Global Interpreter Lock) could be a factor — with up to 11 threads sharing a single GIL, a busy core could starve the orchestration thread.

**Finding: CPU is not the constraint.** STM has 16 cores. Per-core analysis:

| Metric | Slow sessions | Normal sessions | p-value |
|:--|--:|--:|--:|
| Avg max core % | 39.8 | 25.8 | 0.42 |
| Max max core % | 75.0 | 80.1 | 0.001 |
| Avg P95 core % | 25.7 | 17.3 | 0.010 |
| % samples with any core >80% | 0.0 | 2.0 | 0.001 |

No core approaches saturation. The max single-core usage is actually *negatively* correlated with gap duration (rho=-0.179) — normal sessions push cores harder because they're doing productive burst work, while slow sessions are waiting on I/O. The GIL is not the bottleneck.

## Eyelink Stop Sequence: The Largest Single Bottleneck

### Timing breakdown

Using `log_application` timestamps for the Eyelink lifecycle messages (`Setting Stop Signal`, `Exiting Record Thread`, `Starting Record Thread`), we measured the Eyelink stop overhead across 1,873 task transitions (last 3 months):

| Phase | What happens | Median | P75 | P90 | P95 |
|:--|:--|--:|--:|--:|--:|
| Thread join | `recording=False` → `stopRecording()` → `closeDataFile()` | **0.7s** | 0.7s | 0.7s | 0.7s |
| Post-exit | `receiveDataFile()` + `edf_to_ascii()` + next task setup | **16.5s** | 28.8s | 64.2s | 118.9s |
| **Total** | Stop signal → next task starts | **17.2s** | 30.2s | 86.0s | 198.5s |

The thread join is negligible and rock-solid at 0.7s. **Virtually all of the Eyelink overhead is in the post-exit phase.**

### What happens in the post-exit phase

After the recording thread exits, `stop()` runs two operations sequentially:

1. **`receiveDataFile()`** — transfers the .edf file from the Eyelink hardware (at 192.168.100.15) to STM disk over Ethernet.
2. **`edf_to_ascii()`** — runs `edf2asc.exe` as a subprocess to convert the binary .edf to ASCII format. This blocks until conversion completes.

### File transfer is trivial

From sample count log messages, the typical EDF file is **4.3 MB** (median 57K samples at 1000 Hz binocular). Transfer times:

| Network speed | Median transfer time | Max (77 MB file) |
|:--|--:|--:|
| 100 Mbps | 0.3s | 6.1s |
| 1 Gbps | 0.03s | 0.6s |

Even at 100 Mbps, the transfer is well under 1 second for most tasks. **The entire 16.5s median overhead is almost certainly `edf2asc.exe`.**

### The conversion is the bottleneck

`edf2asc.exe` is a CPU-bound executable from SR Research that parses binary EDF data and writes verbose ASCII text (significant size expansion). For a 4.3 MB EDF file with binocular gaze data, events, and messages, this takes 15+ seconds. Under memory pressure, it takes longer due to page faults during the text buffer allocations.

This runs as a blocking `subprocess.run()` call — the Eyelink's `stop()` method cannot return until `edf2asc.exe` completes, which means the `RecordingStopped` message cannot be sent, which means the next task cannot start.

### Recommendation: Defer conversion

**Deferring `edf_to_ascii()` to after the session would eliminate ~16s from every inter-task transition.** This is the single largest actionable improvement identified in this analysis.

The .edf file is already safely on the STM disk after `receiveDataFile()` completes (~0.3s). The ASCII conversion is a convenience for downstream analysis and does not need to happen between tasks. Options:

1. **Defer to end of session** — run all conversions after `TasksFinished`. The Eyelink hardware only needs ~4 MB of storage per task, so a 28-task session uses ~120 MB — well within the Portable Duo's storage capacity.
2. **Defer to a background process** — queue conversions and run them asynchronously without blocking task transitions.
3. **Eliminate conversion entirely** — if downstream analysis can read .edf directly (via pyedfread or similar), the ASCII conversion may not be needed at all.

The transfer (`receiveDataFile`) should remain between tasks to free storage on the Eyelink hardware and ensure data safety.

### Would rewriting in C# help?

- **For the Eyelink overhead:** No — the bottleneck is `edf2asc.exe` (an external executable), not Python. C# would call the same executable and wait the same amount of time.
- **For the swap/memory issue:** Probably not. The bottleneck is OS-level memory management, not language performance. C# would hit the same page fault latency.
- **For baseline device overhead (non-Eyelink):** Possibly. Native device SDKs (RealSense C++ SDK, FLIR Spinnaker C++) would likely have faster start/stop cycles than Python wrappers, potentially reducing the consistent 5-8s camera overhead. The Python wrapper adds serialization, GIL acquisition, and buffer copying overhead.
- **For LSL:** C# bindings are closer to native liblsl and would likely be more performant.

## Thread Contention and Context Switching on ACQ

### Thread inventory during recording

ACQ_0 runs approximately 8-9 Python threads simultaneously during a task, all sharing a single GIL:

| Thread | Device | Activity |
|:--|:--|:--|
| Main | DeviceManager | DB message loop polling |
| Record | Intel_D455_1 | frame capture + LSL push |
| Record | Intel_D455_2 | frame capture + LSL push |
| Record | Intel_D455_3 | frame capture + LSL push |
| Record | FLIR capture | frame capture + LSL push + queue put |
| Save | FLIR write | queue get + compress + disk write |
| Listen | iPhone | socket recv + LSL push |
| Stream | Mic | audio read + LSL push |
| Background | SystemResourceLogger | psutil + DB insert every 10s |

Additionally, 3 Mbient devices fire BLE callbacks in the GIL context (not separate threads, but they do acquire the GIL).

### During recording: GIL contention is manageable

Most threads spend the majority of their time in C extensions (pyrealsense2, PySpin, pyaudio, pylsl) which **release the GIL** during I/O waits. The GIL is only held briefly for Python bytecode — pushing an LSL sample, putting a frame on a queue, incrementing a counter. During steady-state recording, the threads coexist reasonably well.

### During transitions: GIL contention is significant

At stop/start time, the threading architecture creates compounding overhead:

1. **`stop_cameras()` is sequential.** It calls `stop()` then `ensure_stopped()` for each camera one at a time. While waiting for Intel_D455_1 to finish, the FLIR save thread may still be running (draining its queue), holding the GIL periodically. Each GIL acquisition by the FLIR delays the Intel's `pipeline.stop()` completion.

2. **Thread teardown is GIL-heavy.** `thread.join()` involves Python-level synchronization. When 3 Intel cameras + FLIR + Mic all need their threads joined sequentially, each join blocks while other threads are still doing GIL-contended work.

3. **Thread creation at start is also GIL-heavy.** `threading.Thread(target=...).start()` acquires the GIL. Starting 5-7 threads sequentially while Mbient callbacks are still firing adds overhead.

4. **DB message polling on the main thread** requires the GIL + a database round-trip. Between tasks, the main thread polls the DB waiting for `StartRecording`, while background threads from the previous task may still be winding down.

### Estimated impact

Without profiling, a rough estimate:
- Each thread context switch under GIL contention: ~0.01-0.1ms
- With 8 threads and hundreds of switches during a stop/start cycle: **0.5-2s** of accumulated overhead
- This is a fraction of the 5-8s camera baseline overhead, but it compounds with memory pressure (swap makes every context switch more expensive due to TLB flushes and page faults in thread state)

### Interaction with memory pressure

Under swap pressure, context switching becomes more expensive because:
- Thread stacks may be partially swapped out, requiring page-ins on each switch
- TLB (Translation Lookaside Buffer) entries are invalidated on context switches, and rebuilding them requires additional page table walks that may themselves trigger page faults
- The OS scheduler does more work managing the page file, adding kernel-mode overhead to every switch

This creates a feedback loop: more threads → more context switches → more page faults → slower switches → longer transitions → more time for other threads to accumulate GIL contention.

### How the ACQ split helps

Moving the 3 Intel camera threads to ACQ_2 would reduce ACQ_0's thread count from 8-9 to 5-6 during recording, and from ~5 threads to ~2 during stop/start. This roughly halves GIL contention during transitions and isolates the Intel cameras' memory pressure (the likely source of the 51 GB RAM spikes) from the FLIR, Mic, and Mbient devices.

## Disk / SSD Considerations

The machines use SSDs rated at ~4 GB/s write throughput. For context:

- The FLIR at 30fps with ~5 MB frames needs ~150 MB/s sustained — less than 4% of disk capacity. **Disk is not the FLIR bottleneck.**
- Each Intel camera writing .bag files (RGB+depth) at 30Hz needs a similar order of throughput. Three cameras combined still well under disk capacity.
- SSD page fault latency: ~0.1-0.5ms (vs 5-15ms for HDD). Fast, but not free — the overhead is in kernel context switches and TLB flushes, not disk speed.
- The swap impact we observe exists despite fast SSDs, confirming the bottleneck is CPU-side (GIL, page fault kernel overhead) not I/O-side.

## Why Swapping With Abundant Free RAM?

STM has 68.5 GB RAM but only uses ~14-15 GB on slow days — yet swap is elevated. Possible explanations:

1. **Windows proactive swapping (Superfetch/SyMain):** Windows preemptively moves "inactive" pages to the page file to free RAM for file caching, even when RAM isn't full. Between-task idle periods trigger this.
2. **Memory-mapped files:** Device SDKs using memory-mapped I/O show up in swap statistics without traditional RAM exhaustion.
3. **Committed bytes vs active swap:** Windows' swap_used (as reported by psutil) may reflect page file commitment rather than pages actively being paged out.
4. **ACQ peak-driven eviction:** During ACQ RAM spikes (51 GB), Windows evicts pages from other processes. After the spike subsides, those evicted pages remain in swap even though RAM is now free.

## Recommendation: Split ACQ_0 Into Two Processes

### Problem

ACQ_0 currently runs **9 devices** in a single Python process: 3 Intel cameras, FLIR, IPhone, 3 Mbients, and Mic. Because of the GIL (Global Interpreter Lock), all threads in this process — capture, compression, LSL streaming, device management — share a single execution lock. This means:

- The FLIR save thread competes with Intel camera threads, Mbient BLE handlers, and LSL outlets for GIL time
- Memory allocation by any device's buffers affects all other devices via page eviction
- The 51 GB RAM spikes (likely from Intel depth+RGB buffers) cause system-wide swap pressure that degrades all devices

### Proposed split

Move the three Intel cameras to their own acquisition process:

| Process | Machine | Devices |
|:--|:--|:--|
| **ACQ_0** | ACQ | FLIR_blackfly_1, IPhone_dev_1, Mbient_BK/LH/RH, Mic_Yeti |
| **ACQ_2** (new) | ACQ | Intel_D455_1, Intel_D455_2, Intel_D455_3 |
| ACQ_1 | STM | Mouse, Mbient_LF/RF |

### Why this split (rather than isolating FLIR)

1. **The Intels are the heavier problem.** Three RGB+depth cameras at 30Hz each are the most likely source of the 51 GB RAM spikes. Each RealSense SDK instance allocates its own frame buffers for both color and depth streams.
2. **The Intels benefit from being together.** All three use pyrealsense2/librealsense, have similar resource profiles, and may share USB controller bandwidth. Grouping them keeps their shared SDK management in one place.
3. **FLIR + lightweight devices is a reasonable mix.** Without three Intel cameras competing for the GIL, the FLIR's occasional queue backlog would be far less impactful.

### Benefits

- **Each process gets its own GIL.** Intel camera threads no longer starve the FLIR save thread or Mbient BLE handlers.
- **Memory isolation.** Intel RAM spikes (depth buffers, .bag file writes) only affect the Intel process. FLIR, Mbients, and Mic are insulated.
- **Proven pattern.** ACQ_1 on the STM machine already runs as a separate acquisition process. The architecture supports this with a config-only change (add a third entry to the `acquisition` array).
- **No code changes to device implementations.** The FLIR, Intel, and other device code stays the same.

### Tradeoffs

- **One more process to manage** — another Windows Task Scheduler entry, another set of log entries.
- **One more database message round-trip per task transition** — StartRecording/RecordingStopped for ACQ_2. This adds ~5-6s of baseline overhead (Mic-level), but this is likely recovered from the performance improvement.
- **USB bandwidth is unchanged.** If the three Intels share a USB host controller (~5 Gbps shared), process isolation doesn't fix hardware-level USB contention. But it prevents USB contention from cascading into GIL contention for other devices.

### Alternative considered: FLIR to its own process

Moving FLIR alone to a new process would fix the FLIR queue issue but wouldn't address the Intel RAM spikes (which are the larger contributor to system-wide memory pressure). The Intel-isolation split addresses both problems.

## Prioritized Recommendations

After removing `edf2asc.exe` (v0.63.0, ~16s saved per transition), the remaining contributors to inter-task delay are ranked below by estimated impact and implementation effort.

### 1. Split Intel cameras into their own ACQ process (highest priority)

**Estimated impact:** 2-4s per transition from reduced GIL contention and memory isolation.

**Effort:** Config-only change (add a third `acquisition` entry) + deploy script update. No code changes.

This is the highest priority because it addresses multiple problems simultaneously — GIL contention, memory isolation from Intel RAM spikes (51 GB), swap pressure on the FLIR save thread — and it's a proven pattern (ACQ_1 already works this way). See the "Recommendation: Split ACQ_0" section above for the full proposal.

### 2. Schedule periodic machine reboots (quick operational fix)

**Estimated impact:** Eliminates the multi-day swap accumulation on STM that causes slow days (e.g., March 12 at 29.5s vs normal 15s).

**Effort:** Add a weekly overnight reboot to Windows Task Scheduler on STM and ACQ.

STM RAM grows ~1-2 GB per active day from a background process. After 3-4 weeks without a reboot, RAM reaches 30+ GB and swap exceeds 400 MB, correlating with the worst session performance. This is a symptom-level fix — the leaking process should still be identified — but it's immediate and zero-risk.

### 3. Parallelize stop_cameras()

**Estimated impact:** ~1-2s per transition.

**Effort:** Small code change in `DeviceManager.stop_cameras()` (`lsl_streamer.py`). Currently calls `stop()` then `ensure_stopped()` for each camera sequentially. Could signal all cameras to stop first, then wait for all to finish:

```python
# Current (sequential):
for stream in cameras:
    stream.stop()
    stream.ensure_stopped(10)

# Proposed (parallel stop, then wait):
for stream in cameras:
    stream.stop()            # Signal all to stop (non-blocking)
for stream in cameras:
    stream.ensure_stopped(10)  # Wait for all to finish
```

Note: The code already does this two-loop pattern (signal all, then wait all). Verify that the implementation actually executes this way, and that `ensure_stopped` timeouts don't cascade.

### 4. Identify the STM memory-leaking process

**Estimated impact:** Would eliminate the root cause of slow days (rather than mitigating via reboots).

**Effort:** Run Process Explorer or `tasklist /v` on a high-swap day to identify which resident process is consuming the growing memory. Likely candidates: Eyelink Host Application, Dropbox, antivirus, Windows Update agent.

### 5. Reduce DB message round-trip overhead

**Estimated impact:** ~0.5-1s per round-trip, 4+ round-trips per transition = potentially 2-4s total.

**Effort:** Architectural change — would require moving from database-polled messaging to direct socket communication or a lighter message broker. High effort, high risk, but would remove the fundamental latency floor in the current architecture.

### Summary table

| Priority | Action | Impact | Effort | Type |
|--:|:--|:--|:--|:--|
| ~~0~~ | ~~Remove edf2asc~~ | ~~16s~~ | ~~Done (v0.63.0)~~ | ~~Code~~ |
| 1 | Split Intels to ACQ_2 | 2-4s | Config only | Config |
| 2 | Scheduled reboots | Eliminates bad days | Task Scheduler | Operational |
| 3 | Parallelize stop_cameras | 1-2s | Small code change | Code |
| 4 | Identify STM memory leak | Eliminates root cause | Investigation | Operational |
| 5 | Direct messaging | 2-4s | Architectural rewrite | Code |

## Open Items

- [ ] Check SSD SMART health on STM and ACQ machines
- [ ] Check if Superfetch/SyMain is enabled on the machines
- [ ] Run Process Explorer on a high-swap day to identify the leaking resident process on STM
- [ ] Check RealSense SDK buffer allocation patterns (26 "Timeout when waiting for frame!" warnings appeared on slow days)
- [ ] Verify USB controller topology on ACQ — are all three Intels on the same host controller?
- [ ] Implement and test ACQ_0/ACQ_2 split in staging environment

## Scripts

- `extras/resource_analysis.py` — Per-session resource extraction and correlation analysis
