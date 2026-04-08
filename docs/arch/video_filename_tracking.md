# Video Filename Tracking: How It Works and What Broke

## Overview

When neurobooth records data, each device produces files — `.bag` (Intel cameras),
`.avi` (FLIR), `.mov`/`.json` (iPhone), `.edf` (Eyelink). These filenames must be
stored in the `log_sensor_file` database table so downstream pipelines can find them.

The current system routes filenames through an LSL marker stream on the CTR machine.
This document describes the full flow, the bug introduced by `TransitionRecording`,
and the options for fixing it.

## The Data Flow

There are five stages. Understanding each is necessary to see where the bug occurs.

### Stage 1: Device sends filename (ACQ machine)

When a camera device starts recording, it posts a `NewVideoFile` message to the
database message queue, addressed to CTR:

```
FlirCamera.start()         → posts NewVideoFile("FlirFrameIndex", "subj_task_flir.avi")
IntelCamera._prepare_recording() → posts NewVideoFile("Intel1FrameIndex", "subj_task_intel1.bag")
IPhone.start()             → posts NewVideoFile("IPhoneFrameIndex", "subj_task_IPhone.mov")
                             posts NewVideoFile("IPhoneFrameIndex", "subj_task_IPhone.json")
EyelinkTracker.start()     → posts NewVideoFile("EyelinkFrameIndex", "subj_task.edf")
```

These messages travel through the PostgreSQL `message_queue` table. They are not
instant — the message must be written by ACQ, then read by CTR on its next poll
cycle (~250ms).

**Key files:**
- `iout/flir_cam.py:184` — FLIR sends NewVideoFile
- `iout/camera_intel.py:136` — Intel sends NewVideoFile
- `iout/iphone.py:787-789` — iPhone sends two (`.mov` + `.json`)
- `iout/eyelink_tracker.py:188` — Eyelink sends NewVideoFile

### Stage 2: CTR pushes filename to LSL marker stream (CTR machine)

CTR's message reader thread receives the `NewVideoFile` message and dispatches it
to the GUI event loop:

```
SessionController._message_reader()           # reads from DB queue
  → listener.on_new_video_file(stream_name, filename, event)
    → window.write_event_value("-new_filename-", "FlirFrameIndex,subj_task_flir.avi")
```

The GUI event loop picks up the event and pushes it to the `videofiles` LSL outlet:

```python
# gui.py:535-536
elif event == "-new_filename-":
    state.video_marker_stream.push_sample([values[event]])
```

The marker format is a single string: `"StreamName,filename.ext"`.

The `videofiles` stream was created during session preparation:

```python
# session_controller.py:346
self.state.video_marker_stream = marker_stream("videofiles")
```

This is a real LSL `StreamOutlet` of type "Markers". It exists on the CTR machine.

**Key files:**
- `session_controller.py:626-628` — dispatches NewVideoFile to listener
- `gui.py:122-123` — GUI listener forwards to event loop
- `gui.py:535-536` — event loop pushes to LSL marker stream
- `iout/marker.py:11-54` — marker stream creation

### Stage 3: LabRecorderCLI captures the marker in XDF (CTR machine)

CTR runs LabRecorderCLI (via `liesl.Session`) to record all LSL streams into XDF
files. The `videofiles` marker stream is one of the streams being recorded.

When CTR calls `session.start_recording(fname)`, LabRecorderCLI begins writing an
XDF file. Any `push_sample` to the `videofiles` outlet after this point is captured
in the XDF. When CTR calls `stop_recording()`, LabRecorderCLI finalizes the file.

**The critical constraint: markers pushed to the `videofiles` outlet while no
LabRecorderCLI recording is active are lost.** They go to the LSL outlet but no
consumer is capturing them.

**Key files:**
- `session_controller.py:456-470` — `start_lsl_recording()`
- `session_controller.py:472-527` — `stop_lsl_recording()` + background finalize

### Stage 4: split_xdf reads markers from XDF (CTR machine, background thread)

After LabRecorderCLI finalizes the XDF, `split_sens_files()` runs in a background
thread. It parses the XDF and extracts the `videofiles` markers:

```python
# split_xdf.py:69-81
video_files = {}
if "videofiles" in [d["info"]["name"][0] for d in data]:
    video_data = [v for v in data if v["info"]["name"] == ["videofiles"]]
    for d in video_data[0]["time_series"]:
        if d[0] == "":
            continue
        stream_id, file_id = d[0].split(",")  # "FlirFrameIndex,subj_task_flir.avi"
        if stream_id in video_files:
            video_files[stream_id].append(file_id)
        else:
            video_files[stream_id] = [file_id]
```

Each device's data stream is then associated with its video files:

```python
# split_xdf.py:99-106
results.append(DeviceData(
    device_id=device_id,
    device_data=device_data,
    marker_data=marker,
    video_files=video_files[device_name] if device_name in video_files else [],
    ...
))
```

If a device's `NewVideoFile` marker was not captured in this XDF, `video_files` will
not contain an entry for that device, and the video filename will be missing from the
`DeviceData`.

**Key files:**
- `iout/split_xdf.py:56-106` — `parse_xdf()`
- `iout/split_xdf.py:147-190` — `log_to_database()`
- `session_controller.py:529-535` — `_split_and_close()`

### Stage 5: log_to_database writes to log_sensor_file (CTR machine)

For each device, the function builds a file path array and inserts it into the
database:

```python
# split_xdf.py:170-190
sensor_file_paths = [hdf5_file, *dev.video_files]
sensor_file_paths = [f'{session_folder}/{f}' for f in sensor_file_paths]
sensor_file_paths = '{' + ', '.join(sensor_file_paths) + '}'

for sensor_id in dev.sensor_ids:
    vals = [(log_task_id, temporal_resolution, None,
             start_time, end_time, dev.device_id, sensor_id,
             sensor_file_paths)]
    table_sens_log.insert_rows(vals, LOG_SENSOR_COLUMNS)
```

The `sensor_file_path` column contains a PostgreSQL array like:
```
{session/subj_task_R001-FlirFrameIndex-frame.hdf5, session/subj_task_flir.avi}
```

If the video filename was missing from Stage 4, the array only contains the HDF5 file.
Downstream scripts that look for specific video files (`.avi`, `.bag`, `.mov`) in this
array will fail with "log_sensor_file_id not found".

**Note:** Some tasks (pursuit, MOT, hevelius) use `postpone_xdf_split()` instead of
immediate splitting. These write XDF metadata to a backlog file for later processing
by `extras/run_xdf_split_postproces.py`. The same marker-capture problem applies.

## What TransitionRecording Changed

### Before (v0.66.1): Sequential stop-then-start

```
Time →

TASK N running
  │
  ├─ STM: stop_acq() sends StopRecording to ACQ
  │    ACQ: stops devices
  │
  ├─ STM: sends TaskCompletion to CTR
  │    CTR: stop_lsl_recording()
  │         LabRecorderCLI finalizes XDF for Task N
  │         split_xdf runs in background
  │
  ├─ STM: sends TaskInitialization to CTR
  │    CTR: start_lsl_recording()
  │         LabRecorderCLI starts new XDF for Task N+1
  │
  ├─ STM: _start_acq() sends StartRecording to ACQ
  │    ACQ: starts devices
  │    ACQ devices: post NewVideoFile to CTR  ←─── AFTER recording started
  │    CTR: receives NewVideoFile, pushes to videofiles stream
  │         (captured in Task N+1's XDF ✓)
  │
TASK N+1 running
```

Devices start **after** CTR has started the new LSL recording. The `NewVideoFile`
markers are always captured.

### After (v0.70.0): Overlapping stop+start via TransitionRecording

```
Time →

TASK N running
  │
  ├─ STM: stop_acq() sends TransitionRecording to ACQ
  │    ACQ: stops Task N devices
  │    ACQ: starts Task N+1 devices                    ←─── EARLY
  │    ACQ devices: post NewVideoFile to CTR            ←─── TOO EARLY
  │    ACQ: sends RecordingStarted to STM
  │
  ├─ STM: sends TaskCompletion for Task N to CTR
  │    CTR: stop_lsl_recording()
  │         LabRecorderCLI finalizes XDF for Task N
  │
  │    ════════ GAP: no LSL recording active ════════
  │
  │    CTR: processes NewVideoFile from DB queue
  │         pushes marker to videofiles stream
  │         (NO XDF recording → marker LOST ✗)
  │
  ├─ STM: sends TaskInitialization for Task N+1 to CTR
  │    CTR: start_lsl_recording()
  │         LabRecorderCLI starts new XDF for Task N+1
  │         (but the markers were already pushed and lost)
  │
TASK N+1 running
```

The `TransitionRecording` optimization moved device startup earlier — into the
`stop_acq` call of the previous task. Devices now send `NewVideoFile` messages
before CTR has cycled its LSL recording. The markers arrive at CTR during the gap
between recordings and are pushed to the `videofiles` outlet with no XDF consumer.

The markers can also land in Task N's XDF instead of Task N+1's, if CTR processes
the `NewVideoFile` message before it processes `TaskCompletion`. This would put
the wrong filenames in the wrong task's `log_sensor_file` entry.

## Fix Options

### Option 1: Buffer markers on CTR

**What:** Hold `NewVideoFile` markers in a list on CTR. Only push them to the
`videofiles` LSL outlet after the next `start_lsl_recording()` call.

**Implementation:**
- Add a `pending_video_markers: List[str]` to `SessionState`
- In `on_new_video_file()`: append to buffer instead of pushing immediately
- In `start_lsl_recording()`: flush the buffer to the marker stream

**Complexity:** Small (~15 lines). No changes to ACQ, STM, split_xdf, or the
database schema.

**Risk:** If a marker arrives after the recording has already started and the XDF
has moved on, it could still be missed. The buffer approach assumes markers for
task N+1 always arrive before task N+1's recording starts, which is true in practice
because `_start_acq` waits for `RecordingStarted` from ACQ before the task runs.

**Preserves TransitionRecording benefit:** Yes.

### Option 2: Delay device start in TransitionRecording

**What:** Don't start the next task's devices until CTR confirms the new LSL
recording is active. Effectively revert to the sequential timing.

**Implementation:** Add a round-trip: ACQ waits for a "RecordingReady" message
from CTR before starting devices.

**Complexity:** Small (~20 lines), but adds a new message type and a database
round-trip (~250ms+ per transition).

**Risk:** Eliminates the performance benefit of TransitionRecording. The whole
point was to avoid the inter-task gap.

**Preserves TransitionRecording benefit:** No — defeats the purpose.

### Option 3: Write filenames directly to log_sensor_file from ACQ

**What:** Instead of routing filenames through the LSL marker stream, have each
device (or the DeviceManager) write video filenames directly to the `log_sensor_file`
table in the database.

**Implementation:**
- Each device already knows its filename at `start()` time
- ACQ would need access to the `log_task_id` for the current task to write the
  correct row. Currently `log_task_id` is created by STM (`server_stm.py:250`)
  and sent to CTR in `TaskInitialization`, but never sent to ACQ.
- Would require:
  1. Add `log_task_id` to `StartRecording` and `TransitionRecording` messages
  2. STM sends the `log_task_id` when telling ACQ to start recording
  3. ACQ (or DeviceManager) writes filenames to `log_sensor_file` directly
  4. Remove the `videofiles` marker stream and the `NewVideoFile` message path
  5. Update `split_xdf.py` to not rely on `videofiles` markers for filenames
     (the video files would already be in the database)

**Complexity:** Medium (~80-100 lines across 6-8 files). The changes span STM
(message construction), ACQ (database writes), the message schema, split_xdf
(remove video_files parsing or make it a fallback), and session_controller
(remove marker stream creation and NewVideoFile handling).

**Risk:** Requires ACQ to have write access to `log_sensor_file`, which it
currently doesn't do. The `neurobooth_terra` Table class would need to be
available on ACQ (it may already be, since ACQ imports from `neurobooth_terra`
indirectly). Also requires passing `log_task_id` through a code path that
currently doesn't have it.

**Preserves TransitionRecording benefit:** Yes.

### Recommendation

**Option 1 (buffer markers) is the right fix for now.** It's minimal, low-risk,
preserves the performance optimization, and doesn't change the data flow
architecture. The only assumption is that `NewVideoFile` markers for the next task
arrive at CTR before that task's LSL recording starts, which is guaranteed by the
`RecordingStarted` wait in `_start_acq`.

Option 3 is the architecturally "correct" solution — routing filenames through an
LSL marker stream on a different machine was always fragile. But it's 5-6x more
complex than Option 1, touches more files, requires schema changes to messages,
and introduces a new write path to the database from ACQ. It should be considered
as a future improvement, not an urgent fix for the current bug.

Option 2 should be avoided — it reverts the performance gain that motivated
`TransitionRecording` in the first place.
