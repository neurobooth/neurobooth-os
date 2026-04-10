# Video Filename Tracking — Current Design (post #659 re-fix)

This document describes the current mechanism for recording video filenames in
`log_sensor_file` and compares the resulting data to the pre-#611 system.
Intended audience: anyone touching `split_xdf`, `server_acq`, `server_stm`,
`session_controller`, or downstream scripts that read `log_sensor_file`.

For historical context on the bug that motivated the 2026-04 rewrite, see
`video_filename_tracking.md` (describes the LSL marker-stream design and the
gap bug introduced by `TransitionRecording`).

## Mechanism

Filenames travel from the producer (ACQ's DeviceManager or STM's task/eye
tracker code) to CTR via the database `message_queue`, as a `RecordingFiles`
message. CTR accumulates them in an in-memory buffer on the message reader
thread, and passes the buffer contents to `split_xdf` when the matching
`TaskCompletion` arrives.

Each `RecordingFiles` message is **tagged with `fname`**, the unique per-run
identifier:

```
fname = f"{session_name}_{tsk_start_time}_{task_id}"
```

`tsk_start_time` is generated when STM enters `_perform_task` for a given
task and contains hour/minute/second resolution. Repeated runs of the same
task (recalibration, session restart, subject repeats) produce different
`tsk_start_time` values and therefore different fnames. The fname flows
through the same code paths used for file naming, so the buffer key matches
the filename prefix on disk.

`TaskCompletion` carries the same `fname`. When CTR reads it, it pops only
the bucket for that specific fname. Files for other task runs stay untouched.

### Sequence (happy path)

```
STM                    ACQ                    CTR
 │                      │                      │
 ├─ post TransitionRecording(fname=F1) ──────► │
 │                      │                      │
 │                      ├─ start cameras       │
 │                      ├─ post RecordingFiles(fname=F1, files=...) ─────►
 │                      │                      │  buffer[F1] = {...}
 ├─ task runs ...       │                      │
 │                      │                      │
 ├─ post TaskCompletion(fname=F1) ─────────────►
 │                      │                      │  pop buffer[F1]
 │                      │                      │  → split_xdf → log_sensor_file
```

### Sequence (out-of-order, the race #659 was fighting)

```
STM                    ACQ                    CTR
 │                      │                      │
 ├─ post TransitionRecording(fname=F2, task=next) ───►
 │                      │                      │
 │                      ├─ start cameras       │
 │                      ├─ post RecordingFiles(fname=F2, files=...) ───► (inserted as id=N)
 │                      │                      │  buffer[F2] = {...}
 │                      │                      │
 ├─ post TaskCompletion(fname=F1, task=current) ─────────────► (inserted as id=N+1)
 │                      │                      │  pop buffer[F1]
 │                      │                      │  → correctly empty
 │                      │                      │  F2's bucket is still intact
 │                      │                      │
 ├─ post TaskCompletion(fname=F2, task=next) ─────────────►
 │                      │                      │  pop buffer[F2]
 │                      │                      │  → contains F2's files ✓
```

The key property: messages inserted into the DB out of order still get
bucketed correctly because the bucket key is the task-run identifier, not
arrival order or message type grouping.

## Data comparison to pre-#611 system

### `log_sensor_file.sensor_file_path`

**Same data, same format.** The array still contains
`[hdf5_path, video_path_1, video_path_2, ...]` in the same order as before.
The mechanism for collecting the paths is different but the resulting column
value is identical.

Validated by the check script at `extras/sql/check_missing_video_files.sql` —
for a correctly-functioning session, every camera row should contain its
expected video file extension.

### `log_sensor_file.file_start_time` / `file_end_time`

**Same derivation, same values, same bug.** These are still computed by
`compute_clocks_diff()` at XDF split time (see #671). The fname-keyed
buffering change does not touch timestamp computation. If #671 is fixed, the
values become correct; if not, they have the same clock-drift risk as before.

### `log_sensor_file.true_temporal_resolution`

**Same derivation, same values.** Computed from the XDF `time_stamps` array
during split. Unchanged.

### XDF file contents

**One visible difference.** Pre-#611 XDF files contained a `videofiles` LSL
marker stream with samples of the form `"FlirFrameIndex,task_flir.avi"`. The
current XDF files do **not** contain this stream — it was removed in
d0dfbf8 (the first #659 fix) when filename transport moved off LSL and onto
the DB message queue.

Consequences:
- `parse_xdf()` no longer reads the `videofiles` stream. The branch that did
  still exists in the pre-d0dfbf8 code paths but is dead.
- Any external tool that re-opens old XDF files expecting `videofiles` will
  still find it (old files are unchanged); any tool that expects it in
  *new* XDF files will get nothing.
- The `video_files` parameter now flows into `parse_xdf`/`split_sens_files`
  from the CTR buffer, not from the XDF file itself.

### `log_sensor_file` row cardinality

**Same.** Still one row per `(log_task_id, device_id, sensor_id)`. The
multi-sensor devices (Intel `rgb_1` + `depth_1`) still produce two rows per
task, with identical `sensor_file_path` arrays. The FLIR still produces one
row with one hdf5 and one avi. No new rows, no removed rows.

### Failure modes

**Different, and fewer.**

| Failure mode | Pre-#611 | d0dfbf8 (first fix) | Current |
|---|---|---|---|
| LSL gap between recordings (markers lost) | Yes — #659 | No | No |
| Message-order race (next task's files swept into current) | N/A | Yes — #659 regression | No |
| Repeated tasks within a session mixing files | N/A | Yes (task_id collision) | No |
| Downstream missing-video queries | Broken by LSL gap | Broken by order race | Should work |

### Data timing

**Slightly different but invisible.** In the pre-#611 system, filenames
entered `log_sensor_file` during the XDF split, after LabRecorder finalized
the XDF file. In the current system, filenames enter the CTR buffer as soon
as the device's `start()` returns; they're still written to
`log_sensor_file` during the XDF split on the same schedule. The timing of
DB writes is unchanged from the reader's perspective.

## What to look for when validating

Run `extras/sql/check_missing_video_files.sql` (filtered to the target
release) after each session and confirm zero rows. Any row returned means
either:
- A device failed to produce its video file (check device logs), or
- A `RecordingFiles` message was lost or mistagged (check `body.fname`
  values in the `message_queue` table for the session)

## Files and line references

- `neurobooth_os/msg/messages.py` — `RecordingFiles.fname`,
  `TaskCompletion.fname`
- `neurobooth_os/iout/lsl_streamer.py` — `start_recording_devices(filename, fname, task_devices)`
- `neurobooth_os/server_acq.py` — extracts `fname` from
  `StartRecording`/`TransitionRecording`, passes through to
  `start_recording`
- `neurobooth_os/server_stm.py` — constructs `fname` in `_perform_task`,
  threads through to `_get_task_instance` and `TaskCompletion`
- `neurobooth_os/tasks/eye_tracker_calibrate.py` — uses `kwargs["run_fname"]`
  in its `RecordingFiles` message
- `neurobooth_os/session_controller.py` — `task_video_files: Dict[fname, Dict[stream, files]]`;
  message reader buckets by `body.fname`, pops by `TaskCompletion.fname`
- `tests/pytest/test_video_files_race.py` — unit tests including the session
  3185 message-order race and the repeated-task case
