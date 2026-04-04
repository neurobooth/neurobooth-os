# Mbient Crash Analysis — March 31 to April 3, 2026

Analysis of crash logs from the ACQ_0 (acquisition machine) and ACQ_1 (presentation
machine) processes, produced by the `faulthandler`-based crash logging added in early
2026.

Related issue: https://github.com/neurobooth/neurobooth-os/issues/644

## Hardware Configuration

Each acquisition process communicates with its Mbient sensors over BLE through a
single USB Bluetooth dongle:

| Service | Machine | Mbient Devices | BLE Dongle |
|---------|---------|----------------|------------|
| ACQ_0 | ACQ workstation | Mbient_BK_1, Mbient_LH_2, Mbient_RH_2 (3 devices) | 1 shared dongle |
| ACQ_1 | STM workstation | Mbient_LF_2, Mbient_RF_2 (2 devices) | 1 shared dongle |

## Session Summary

### ACQ_0 (acquisition machine)

20 sessions over 4 days. **5 crashed**, all on April 2.

| PID | Time | Error Type | Crash Site |
|-----|------|------------|------------|
| 25032 | Apr 2 13:12 | access violation (x4) | `create_data_fusion_processor`, `setup`, `close` |
| 22572 | Apr 2 16:27 | Aborted | `_private_write_async` |
| 744 | Apr 2 16:42 | Aborted | `_private_write_async` |
| 10556 | Apr 2 16:47 | access violation (x3) | `create_data_fusion_processor`, `close` (x2) |
| 25352 | Apr 2 17:27 | access violation (x3) | `push_sample` (via mbient callback), `close` (x2) |

### ACQ_1 (on STM/presentation machine)

21 session pairs (ACQ_1 + STM) over 4 days. **5 crashed** (4 on April 2, 1 on April 3).

| PID | Time | Error Type | Crash Site |
|-----|------|------------|------------|
| 110228 | Apr 2 16:27 | Aborted | `_private_write_async` |
| 102728 | Apr 2 16:42 | Aborted | `_private_write_async` |
| 107992 | Apr 2 16:47 | Aborted | `_private_write_async` |
| 93868 | Apr 2 17:14 | Aborted + 0xc000001d + access violation | `_private_write_async`, then `close` (x2) |
| 101844 | Apr 3 13:30 | 0xc000001d + access violation | `close` (x2) |

### Cross-machine correlation

The April 2 crashes were tightly synchronized between the two machines:

| Time | ACQ_0 | ACQ_1 |
|------|-------|-------|
| 13:12 | CRASH (access violation) | no crash |
| 16:27 | CRASH (access violation) | CRASH (Aborted) |
| 16:42 | CRASH (Aborted) | CRASH (Aborted) |
| 16:47 | CRASH (access violation) | CRASH (Aborted) |
| 17:14 | no crash | CRASH (Aborted + 0xc000001d) |
| 17:27 | CRASH (access violation + close) | no crash |

Three of the crashes hit both machines simultaneously, suggesting the Mbient sensor
hardware itself became unstable (BLE radio interference, sensor firmware issue, or
battery degradation), causing both machines' connections to fail and triggering native
library bugs.

## Error Types

All crashes originate in the MetaWear/warble native C libraries. None are catchable
Python exceptions.

- **"Windows fatal exception: access violation"** (0xc0000005) — SEGFAULT. The native
  code dereferenced invalid memory. Kills the entire process.
- **"Fatal Python error: Aborted"** — The native library called `abort()`, likely from
  a failed internal assertion. Kills the entire process.
- **"Windows fatal exception: code 0xc000001d"** (STATUS_ILLEGAL_INSTRUCTION) — The
  CPU attempted to execute an invalid instruction, indicating corrupted vtables, freed
  function pointers, or stack corruption in native code. Kills the entire process.

Every crash killed the main Python process (`server_acq.py`). The process was then
relaunched by the supervisor/operator.

## Root Cause: Thread Safety in the Native MetaWear Library

### Crash site 1: Parallel device initialization (`create_data_fusion_processor`)

ACQ_0 was initializing its 3 Mbient devices in parallel via `ThreadPoolExecutor`
(devices were listed in `ASYNC_STARTUP`). The `create_data_fusion_processor` function
calls directly into `libmetawear`:

```python
libmetawear.mbl_mw_dataprocessor_fuser_create(
    sensor_signals.accel_signal, signals, 1, None, callback_manager.callback
)
```

When multiple threads call `libmetawear` C functions concurrently — even for different
physical devices — they share internal global state, causing access violations.

**Evidence (PID 10556):** Two thread pool workers were simultaneously inside the native
library — one in `create_data_fusion_processor` (crashed), the other in
`metawear.py:404 connect` — while the main thread waited in
`lsl_streamer.py create_streams` → `as_completed`.

**Fix applied:** Mbient devices were removed from `ASYNC_STARTUP` so `create_streams`
initializes them sequentially. `mbient_reset` was also changed from
`ThreadPoolExecutor` to sequential iteration.

### Crash site 2: Concurrent BLE write callbacks (`_private_write_async`)

This was the dominant crash on ACQ_1 (4 of 5 crashes). The crash path runs inside
native MetaWear callback threads:

```
gattchar.py:47 completed          ← previous BLE op finishes on native thread
metawear.py:437 completed         ← triggers next write
metawear.py:442 _write_char_async
gattchar.py:71 write_without_resp_async
gattchar.py:53 _private_write_async  ← ABORT
```

With multiple Mbient devices connected and streaming, each device has its own native
callback thread. Two concurrent calls into warble's BLE write layer from different
native threads hit the same thread-safety issue — just in the communication path rather
than the setup path.

These crashes cannot be prevented by a Python-level lock because the callbacks fire
from within the native C library, outside of Python's control.

### Crash site 3: Disconnect callbacks (`attempt_reconnect`)

The `on_disconnect` callback is registered on each device:

```python
self.device_wrapper.on_disconnect = lambda status: self.attempt_reconnect(status)
```

When a device disconnects, this fires on a native MetaWear event thread, calling
`_ble_connect()` → `setup()` → `create_data_fusion_processor()`. If multiple devices
disconnect around the same time, their callbacks fire concurrently, re-entering native
library code in parallel.

**Evidence (PID 25032):** The crash thread entered through
`warble/gatt.py:76 event_fired` → `metawear.py:472 event_handler` →
`attempt_reconnect` → `setup` → access violation.

**Fix proposed:** Add a class-level `RECONNECT_LOCK` to serialize reconnection attempts
across devices (see issue #644).

### Crash site 4: Cleanup (`close`)

`mbient.py:822 close` crashes reliably after any of the above failures. Once native
state is corrupted by a prior crash, the cleanup path (called by `close_streams` during
session teardown) dereferences the corrupted state and produces a secondary access
violation. This creates the "double recording" pattern where 2-3 fatal exception dumps
appear per session.

## BLE Radio Contention

Each Bluetooth dongle has a single radio using time-division multiplexing for multiple
BLE connections. With 3 devices on ACQ_0's dongle and 2 on ACQ_1's dongle:

1. Each connected device gets periodic time slots for data transfer.
2. At high IMU sample rates, the radio struggles to service all connections promptly.
3. A device that misses its connection interval disconnects.
4. Reconnection attempts (BLE scanning + connection setup) monopolize the radio.
5. Other devices miss their intervals during the reconnect → cascade disconnections.

The April 2 afternoon cluster (4 crashes in ~75 minutes) looks like a cascade failure
where one disconnection triggered reconnection attempts that starved the other devices.

### Multi-adapter limitation

Adding more USB Bluetooth dongles does not help on Windows. The MetaWear SDK constructor
(`MetaWear(mac_address)`) exposes no adapter selection parameter on Windows. The WinRT
BLE API routes all connections through the system's default adapter. On Linux, the SDK
supports `hci_mac` for adapter selection, but the acquisition machines run Windows.

## Mitigations

### Applied

- Removed Mbient devices from `ASYNC_STARTUP` — device initialization is now sequential.
- Changed `mbient_reset` from `ThreadPoolExecutor` to sequential iteration.

### Proposed (issue #644)

- Add `RECONNECT_LOCK` to serialize `attempt_reconnect` callbacks across devices.

### Applied (close() hardening)

- **Reordered `close()` to unsubscribe before stop().** `stop()` disables the underlying
  sensors, which invalidates the fusion processor's input signals. Calling
  `mbl_mw_datasignal_unsubscribe` after disable can trigger SIGILL / access violations
  in the native library. The new order: unsubscribe → stop → disconnect.
- **Isolated per-signal cleanup.** Each `mbl_mw_datasignal_unsubscribe` call is
  individually guarded so one corrupted handle does not prevent cleanup of others.
  C-level crashes still cannot be caught by Python, but Python-level failures are
  contained.
- **Cleared `subscribed_signals` after unsubscribe** to prevent double-unsubscribe if
  `close()` is reached again.

### Potential further improvements

- **USB instead of BLE** for one or more sensors. The code already supports USB
  connections (`device.usb.is_connected`). USB eliminates both radio contention and BLE
  thread-safety issues for those devices.
- **Reduce devices per dongle.** Redistributing from 3+2 to 2+2 with one sensor on USB
  would reduce radio pressure on ACQ_0's dongle.
- **Increase BLE connection intervals** to give the radio more scheduling headroom, at
  the cost of reduced sample rate.

## Background Threads (not crash-related)

Every crash dump includes these threads in normal blocking states. They are not involved
in the crashes but appear in every `faulthandler` dump because it prints all threads:

- **SSH tunnel threads** (sshtunnel/paramiko): 3 tunnels, each with `_redirect` handler,
  `serve_forever`, and paramiko `transport.run` threads. Used for database connections.
- **Camera threads**: 3x Intel RealSense `record`, 1-2x FLIR `camCaptureVid`/`record`
  (ACQ_0 only).
- **iPhone listener**, **microphone stream**, **log_manager**: all blocking on I/O.
