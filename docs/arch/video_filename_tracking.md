# Video Filename Tracking

This document describes how recording filenames end up in the
`log_sensor_file` database table. Intended audience: anyone touching
`split_xdf`, `server_acq`, `server_stm`, `session_controller`, or
downstream scripts that read `log_sensor_file`.

The current design landed in **#686 ("Coordinate log_sensor_file
registration through the database")**. Earlier iterations are visible in
git history: pre-#611 used an LSL `videofiles` marker stream; #678
added a fname-keyed `RecordingFiles` message + CTR buffering pipeline
that #686 then replaced.

## Mechanism

Each machine writes its own `log_sensor_file` rows directly, at the
moment it creates the files. Nothing flows through CTR for filename
purposes; CTR's only job in the file pipeline is the subsequent XDF
post-processing step that fills in timing fields.

```
STM                    ACQ                              CTR
 │                      │                                │
 ├─ pre-create log_task                                  │
 │  for next task                                        │
 │  (next_log_task_id)                                   │
 │                      │                                │
 ├─ TransitionRecording(log_task_id) ─────────────►      │
 │                      │                                │
 │                      ├─ device.start() per camera     │
 │                      ├─ _register_sensor_files writes │
 │                      │  log_sensor_file row(s) with   │
 │                      │  paths, NULL timing            │
 │                      │                                │
 ├─ eye_tracker.start()                                  │
 ├─ _register_eyetracker_files writes EDF row(s)         │
 │                      │                                │
 ├─ task runs ...       │                                │
 │                      │                                │
 ├─ TaskCompletion ──────────────────────────────►       │
 │                      │                                │  stop_lsl_recording
 │                      │                                │  → postpone_xdf_split
 │                      │                                │
 │                      │                                │  (later) split_xdf
 │                      │                                │  → log_to_database
 │                      │                                │  UPDATEs timing,
 │                      │                                │  prepends HDF5 path
```

The result: every camera and the EyeTracker have a `log_sensor_file`
row before the task even ends. The XDF post-processing step *fills in*
timing fields and the HDF5 path; it does not create the row from
scratch (except as a fallback — see below).

## ACQ early write — `DeviceManager._register_sensor_files`

`start_recording_devices(filename, fname, task_devices, log_task_id)`
accepts the `log_task_id` that STM created for the task. After
launching every camera in parallel and collecting the file basenames it
created, the method calls `_register_sensor_files`, which inserts one
`log_sensor_file` row per `(device_id, sensor_id)` with:

- `log_task_id` — from the STM-supplied value
- `device_id` / `sensor_id` — read off the Device instance
- `sensor_file_path` — `{session_folder}/{basename}` for each created file
- `file_start_time` / `file_end_time` / `true_temporal_resolution` — `NULL`

Failures are logged but not raised. A database hiccup must not stop a
recording; the XDF split's INSERT fallback (see below) registers the
file later if the early write was missed. See
`neurobooth_os/iout/lsl_streamer.py` (`start_recording_devices`,
`_register_sensor_files`).

## STM early write — `_register_eyetracker_files`

EyeTracker `.edf` files are written on STM, not ACQ, so STM mirrors
the ACQ pattern. Inside `_get_task_instance`, after
`session.eye_tracker.start(edf_fname)` returns the basenames, STM
calls `_register_eyetracker_files(session, log_task_id, basenames,
task_args)`, which inserts the same shape of `log_sensor_file` row
(paths only, NULL timing) for each EyeTracker sensor. Same failure
policy: log and continue.

See `neurobooth_os/server_stm.py` (`_get_task_instance`,
`_register_eyetracker_files`).

## `log_task_id` threading — STM pre-creates, ACQ consumes

ACQ needs `log_task_id` *before* it starts recording the next task,
which is earlier than the task is normally logged. STM pre-creates the
`log_task` row at the end of the current task, alongside its
`stop_acq → TransitionRecording` flow:

1. `_perform_task` for task N finishes the stimulus and calls
   `stop_acq`.
2. STM calls `meta.make_new_task_row(...)` for task N+1 and stashes
   the ID in `session.next_log_task_id`. `log_task_params` is logged
   here too, so `log_device_param` rows exist before any device starts.
3. STM posts `TransitionRecording(log_task_id=session.next_log_task_id, ...)`
   to ACQ. ACQ launches devices and uses that ID for its early write.
4. When `_perform_task` for task N+1 begins, it re-uses
   `session.next_log_task_id` instead of creating a new row, then
   clears the field.

If the session is cancelled or crashes between steps 3 and 4, the
pre-created `log_task` row stays in the database with `task_id = NULL`
— a clear signal that the task started recording but never completed.
Files registered against that `log_task_id` exist in `log_sensor_file`
with NULL timing.

`StartRecording` and `TransitionRecording` both carry an
`Optional[str]` `log_task_id` field. When `None` (e.g. an old STM
talking to a new ACQ during a rolling deploy, or an internal code path
that doesn't have a task ID), ACQ skips the early write and the XDF
split's INSERT fallback handles the row later.

See `neurobooth_os/server_stm.py` (`_perform_task`, `stop_acq`,
`_cancel_transition`) and `neurobooth_os/msg/messages.py`
(`StartRecording`, `TransitionRecording`).

## XDF post-processing — `split_xdf.log_to_database`

After LabRecorder finalises the XDF, `log_to_database` walks every
`DeviceData` and updates the corresponding `log_sensor_file` row.
Three cases are handled in order:

1. **Early row exists, HDF5 path not yet in it (the common case).**
   ```sql
   UPDATE log_sensor_file
   SET true_temporal_resolution = %s,
       file_start_time = %s,
       file_end_time = %s,
       sensor_file_path = ARRAY[%s]::text[] || sensor_file_path
   WHERE log_task_id = %s
     AND device_id = %s
     AND sensor_id = %s
     AND NOT (sensor_file_path @> ARRAY[%s]::text[])
   ```
   Prepends the HDF5 path and fills in timing.

2. **Early row exists, HDF5 path already present (idempotent re-run).**
   The first UPDATE matches zero rows (the `NOT @>` guard fails). A
   second UPDATE without the array-mutation just refreshes timing
   fields, so re-running post-processing on the same XDF is safe.

3. **No early row at all (fallback).** Both UPDATEs match zero rows.
   `log_to_database` falls back to the original `INSERT` path,
   producing a row that contains only the HDF5 path — no video files.
   The neurobooth-terra copy script then warns "log_sensor_file_id not
   found" for any video file in the session, which serves as a canary
   that the early write or the entire registration pipeline is broken.

See `neurobooth_os/iout/split_xdf.py` (`log_to_database`).

## What this design replaces

The earlier (#678) design routed every recording filename through CTR
as a `RecordingFiles` message, which CTR buffered by `fname` and fed
to `split_xdf` on `TaskCompletion`. That pipeline is gone:

- ACQ no longer sends `RecordingFiles`. The class still exists in
  `msg/messages.py` for backward compatibility but is unreferenced —
  scheduled for removal once any external consumers are confirmed gone.
- CTR's `task_video_files` buffer and the `video_files` parameters
  threaded through `on_task_finished` / `stop_lsl_recording` /
  `postpone_xdf_split` / `split_sens_files` / `parse_xdf` were all
  removed.
- The XDF backlog format simplified accordingly (no JSON video-files
  blob).

The motivation: file registration now happens on the same machine that
creates the file, at the same moment, with no inter-machine
coordination needed. A break anywhere in the old chain (cancel, crash,
LSL gap during `TransitionRecording`, message-order race) used to
leave files orphaned on disk; now the `log_sensor_file` row is in
place before the file is even closed.

## Failure modes

| Scenario                         | `log_task.task_id` | `log_sensor_file` row | Copy-script action |
| -------------------------------- | ------------------ | --------------------- | ------------------ |
| Normal completion                | set                | yes, timing filled    | transfer           |
| User abort during task ('q')     | set                | yes, timing filled    | transfer           |
| Cancel before `_perform_task`    | NULL               | yes, NULL timing      | **skip**           |
| Crash before `_perform_task`     | NULL               | yes, NULL timing      | **skip**           |
| Database unreachable for early write | set            | row created later by XDF split fallback (HDF5 only) | transfer + canary warning for missing video |
| Bug: row never created           | --                 | missing               | **canary warning** |

The neurobooth-terra `dataflow.copy_files` query JOINs `log_task` and
filters out rows where `log_task.task_id IS NULL`, so files from
cancelled or crashed tasks are silently skipped. The "log_sensor_file_id
not found" warning is reserved for the bug case (missing row entirely)
and is the load-bearing canary for this whole pipeline — keep it.

## Validation

`extras/sql/check_missing_video_files.sql` returns zero rows on a
healthy session. Any row returned means either:

- A device failed to produce its expected video file (check device
  logs for that session), or
- Both the early write and the XDF split fallback failed (check the
  ACQ log for "Early log_sensor_file write failed" and the CTR log
  for split-related errors).

## Key code references

| File                                              | Role                                                                        |
| ------------------------------------------------- | --------------------------------------------------------------------------- |
| `neurobooth_os/iout/lsl_streamer.py`              | `DeviceManager.start_recording_devices`, `_register_sensor_files`           |
| `neurobooth_os/server_stm.py`                     | `_perform_task`, `_register_eyetracker_files`, `next_log_task_id` lifecycle |
| `neurobooth_os/server_acq.py`                     | extracts `log_task_id` from `StartRecording` / `TransitionRecording`        |
| `neurobooth_os/msg/messages.py`                   | `StartRecording.log_task_id`, `TransitionRecording.log_task_id`             |
| `neurobooth_os/iout/split_xdf.py`                 | `log_to_database` UPDATE-or-INSERT                                          |
| `extras/sql/check_missing_video_files.sql`        | post-session validation query                                               |
| `neurobooth-terra/neurobooth_terra/dataflow.py`   | `copy_files` JOIN filter that drops cancelled-task files                    |
