# Plan: Database-coordinated file registration

## Context

### The problem

When STM sends `TransitionRecording` to ACQ, devices immediately start recording
and create files on disk for the **next** task. If the session is then cancelled or
STM crashes before the next `_perform_task` runs, those files become orphans: they
exist on disk but have no `log_task` or `log_sensor_file` rows. The downstream copy
script (neurobooth-terra `dataflow.py`) reports "log_sensor_file_id not found" for
each orphan, and the files are transferred to the destination without tracking.

### Why the current design is fragile

The `log_sensor_file` entry for a recording depends on a long chain completing
without interruption:

```
device.start() creates files on disk                          (ACQ, immediate)
       |
task runs                                                     (STM)
       |
stop_acq / TaskCompletion                                     (STM -> CTR)
       |
RecordingFiles buffered, popped by fname                      (CTR)
       |
stop_lsl_recording -> postpone_xdf_split                      (CTR)
       |
postprocess_xdf_split -> split_sens_files -> log_to_database  (CTR, deferred)
```

Any break in this chain — crash, cancel, error — means files exist on disk with no
database registration. The data needed for the entry is scattered across three
machines and only assembled at the very end of the pipeline. The video filename
threading through CTR (RecordingFiles -> buffer -> backlog -> XDF split) was added
in commits 4fba312, b52164c8, 6ccbe04b to fix #659 but adds fragility: more moving
parts across more machines.

### The fix

Use the database as the coordination point. ACQ writes `log_sensor_file` rows
immediately after creating files. ACQ has device_id, sensor_ids, and file paths
natively. The only value it's missing is `log_task_id`, which STM can pass through
the existing `TransitionRecording` message.

This makes the video filename threading through CTR unnecessary. The
RecordingFiles buffering, fname-keyed popping, backlog serialization, and
video_files parameters through the XDF split pipeline can all be removed —
simplifying session_controller.py, split_xdf.py, gui.py, and the backlog format.

Timing fields (`file_start_time`, `file_end_time`, `temporal_resolution`) remain
NULL until XDF post-processing fills them in. The HDF5 filename is appended to
`sensor_file_path` during post-processing.

## Changes

### 1. STM: Pre-create `log_task` for the next task (server_stm.py)

**In `_perform_task`, before `stop_acq` (~line 325):**

When `_immediately_next_task_records()` returns a next task, create its `log_task`
row early so the ID is available for the TransitionRecording message:

```python
next_rec_task = _immediately_next_task_records(session, task_id)
if next_rec_task is not None:
    session.next_task_start_time = datetime.now().strftime("%Hh-%Mm-%Ss")
    # Pre-create log_task for next task so ACQ can reference it
    with meta.get_database_connection() as conn:
        session.next_log_task_id = meta.make_new_task_row(conn, subj_id)
        meta.log_task_params(conn, session.next_log_task_id,
                             device_log_entry_dict,
                             session.task_func_dict[next_rec_task])
stop_acq(session, task_args, next_task_id=next_rec_task)
```

**In `_perform_task`, at the start of the recording path (~line 275):**

Check if a `log_task` was pre-created for this task:

```python
if session.next_log_task_id is not None:
    log_task_id = session.next_log_task_id
    session.next_log_task_id = None
    # log_task_params already called during pre-creation
else:
    with meta.get_database_connection() as conn:
        log_task_id = meta.make_new_task_row(conn, subj_id)
        meta.log_task_params(conn, log_task_id, ...)
```

**In `_cancel_transition` (~line 507):**

Reset `session.next_log_task_id = None`. The pre-created `log_task` row stays in the
database with `task_id = NULL` — a clear signal that the task never completed.

**New field on StmSession (stm_session.py):**

```python
next_log_task_id: Optional[str] = None
```

**Files:** `server_stm.py`, `stm_session.py`

### 2. Thread `log_task_id` through TransitionRecording (messages.py, server_stm.py)

Add one Optional field to two message classes:

```python
class StartRecording(MsgBody):
    fname: str
    task_id: str
    frame_preview_device_id: Optional[str] = None
    session_name: str
    log_task_id: Optional[str] = None          # NEW

class TransitionRecording(MsgBody):
    fname: str
    task_id: str
    frame_preview_device_id: Optional[str] = None
    session_name: str
    log_task_id: Optional[str] = None          # NEW
```

**In `stop_acq` (~line 541):** Set `log_task_id=session.next_log_task_id` on the
TransitionRecording body.

**In `_start_acq` (~line 579):** Set `log_task_id` on the StartRecording body when
available (for the first task, the ID is created normally in `_perform_task` and is
available by the time `_start_acq` runs).

Defaults to `None` — old ACQ code that doesn't understand this field simply ignores
it. New ACQ code that receives `None` skips the early write. Safe for rolling
deploys.

**Files:** `messages.py`, `server_stm.py`

### 3. ACQ: Write `log_sensor_file` rows after device start (lsl_streamer.py)

**In `DeviceManager.start_recording_devices` (~line 256):**

Add a `log_task_id` parameter. After collecting file basenames from all devices,
write `log_sensor_file` rows:

```python
def start_recording_devices(self, filename, fname, task_devices,
                            log_task_id=None):
    # ... existing device start logic, collect all_files ...

    # Early registration: write log_sensor_file rows immediately
    if log_task_id is not None:
        self._register_sensor_files(log_task_id, fname, cameras)

    return all_files
```

New private method:

```python
def _register_sensor_files(self, log_task_id, fname, cameras):
    """Write log_sensor_file rows for files just created by device.start()."""
    from neurobooth_terra import Table
    try:
        conn = meta.get_database_connection()
        table = Table("log_sensor_file", conn=conn)
        _, session_folder = os.path.split(os.path.dirname(cameras[0].video_filename))
        for device in cameras:
            basenames = [os.path.basename(f) for f in device.created_files]
            sensor_file_paths = [f'{session_folder}/{b}' for b in basenames]
            pg_array = '{' + ', '.join(sensor_file_paths) + '}'
            for sensor_id in device.sensor_ids:
                table.insert_rows(
                    [(log_task_id, None, None, None, None,
                      device.device_id, sensor_id, pg_array)],
                    cols=LOG_SENSOR_COLUMNS,
                )
        conn.close()
    except Exception as e:
        self.logger.error(f"Early log_sensor_file write failed: {e}")
```

The `try/except` ensures a database failure doesn't prevent recording. The entry
will be created later during XDF post-processing as a fallback.

**In `server_acq.py`:** Pass `log_task_id` from the message through to
`start_recording` -> `start_recording_devices`:

```python
# StartRecording handler (~line 148):
log_task_id = getattr(msg_body, 'log_task_id', None)
start_recording(device_manager, filename, fname, task_args[task].device_args,
                log_task_id=log_task_id)

# TransitionRecording handler (~line 170):
log_task_id = getattr(msg_body, 'log_task_id', None)
start_recording(device_manager, filename, fname, task_args[task].device_args,
                log_task_id=log_task_id)
```

**Files:** `lsl_streamer.py`, `server_acq.py`

### 4. Remove video_files threading from CTR and XDF split pipeline

With ACQ writing `log_sensor_file` entries directly, the video filename pipeline
through CTR is no longer needed. This removes the work from #659 commits 4fba312,
b52164c8, 6ccbe04b and simplifies the codebase.

**session_controller.py:**
- Remove `RecordingFiles` handler (lines 641-648). Replace with a no-op or remove
  entirely (messages will log as "Unhandled" at debug level).
- Remove `task_video_files` dict from `SessionState` (line 279).
- In `TaskCompletion` handler (lines 622-639): remove fname-keyed pop of
  video_files. Just call `self.listener.on_task_finished(body.task_id,
  str(body.has_lsl_stream))` — no video_files parameter.
- Remove `video_files` parameter from `stop_lsl_recording` (line 478). Remove
  the video_files pass-through to `postpone_xdf_split` (line 532).

**gui.py:**
- In `task_finished` handler (~line 514): remove video_files from the unpacked
  tuple. Drop the parameter from `stop_lsl_recording()` call.

**headless_listener.py:**
- Remove `video_files` parameter from `on_task_finished` (line 79).

**Listener interface (session_controller.py ~line 90):**
- Remove `video_files` from `on_task_finished` signature.

**split_xdf.py:**
- Remove `video_files` parameter from `postpone_xdf_split` (line 213).
  Backlog format simplifies to `{xdf_path},{task_id},{log_task_id}` — no JSON blob.
- Remove `video_files` parameter from `postprocess_xdf_split` parsing (line 247).
- Remove `video_files` parameter from `split_sens_files` (line 28).
- Remove `video_files` parameter from `parse_xdf` (line 62).
- Remove `video_files` field from `DeviceData` namedtuple (line 54).

**RecordingFiles messages:** Stop sending them. Remove from:
- `DeviceManager.start_recording_devices` (lsl_streamer.py ~line 287-290)
- EyeTracker sends in `server_stm.py` (~line 376-381) and
  `eye_tracker_calibrate.py` (~line 23-26)

The `RecordingFiles` class in `messages.py` can be kept (for backward compat during
rolling deploy) or removed in a follow-up.

**Files:** `session_controller.py`, `gui.py`, `headless_listener.py`,
`split_xdf.py`, `lsl_streamer.py`, `server_stm.py`, `eye_tracker_calibrate.py`

### 5. XDF split: UPDATE timing + append HDF5 path (split_xdf.py)

**In `log_to_database` (~line 144):**

Replace the current INSERT with an UPDATE-or-INSERT pattern. The early-created row
has video paths; post-processing adds timing fields and prepends the HDF5 path:

```python
for dev in device_data:
    time_offset = compute_clocks_diff()
    timestamps = dev.device_data["time_stamps"]
    start_time = datetime.fromtimestamp(timestamps[0] + time_offset).strftime(...)
    end_time = datetime.fromtimestamp(timestamps[-1] + time_offset).strftime(...)
    temporal_resolution = 1 / np.median(np.diff(timestamps))

    _, session_folder = os.path.split(os.path.dirname(dev.hdf5_path))
    hdf5_basename = f'{session_folder}/{os.path.basename(dev.hdf5_path)}'

    for sensor_id in dev.sensor_ids:
        # Try UPDATE first (row created by ACQ early write)
        cursor.execute("""
            UPDATE log_sensor_file
            SET true_temporal_resolution = %s,
                file_start_time = %s,
                file_end_time = %s,
                sensor_file_path = ARRAY[%s] || sensor_file_path
            WHERE log_task_id = %s AND device_id = %s AND sensor_id = %s
        """, (temporal_resolution, start_time, end_time, hdf5_basename,
              log_task_id, dev.device_id, sensor_id))

        if cursor.rowcount == 0:
            # No early row — INSERT full row (fallback for old code / failed early write)
            sensor_file_paths = '{' + hdf5_basename + '}'
            table_sens_log.insert_rows(
                [(log_task_id, temporal_resolution, None, start_time, end_time,
                  dev.device_id, sensor_id, sensor_file_paths)],
                LOG_SENSOR_COLUMNS)
```

The `ARRAY[%s] || sensor_file_path` prepends the HDF5 path to the existing video
paths array. No need for a unique index — the UPDATE uses a WHERE clause, not
ON CONFLICT.

**Files:** `split_xdf.py`

### 6. EyeTracker files on STM (server_stm.py)

EyeTracker `.edf` files are written on STM, not ACQ. STM writes their
`log_sensor_file` entries directly using the same pattern as ACQ:

**In `_get_task_instance` (~line 374), after `eye_tracker.start()`:**

Write the `log_sensor_file` entry immediately. STM has device_id and sensor_ids
from the EyeTracker device object, and log_task_id from the current task.

No RecordingFiles message needed (removed in step 4).

**Files:** `server_stm.py`

### 7. Copy script: Filter incomplete tasks (neurobooth-terra)

**In `dataflow.py`, `copy_files` (~line 208):**

Change the per-file lookup to JOIN with `log_task` and exclude incomplete tasks:

```python
cursor.execute("""
    SELECT lsf.log_sensor_file_id
    FROM log_sensor_file lsf
    JOIN log_task lt ON lsf.log_task_id = lt.log_task_id
    WHERE lsf.sensor_file_path @> ARRAY[%s]
      AND lt.task_id IS NOT NULL
""", (fname,))
rows = cursor.fetchall()
```

This is the **only call site** that needs to change in neurobooth-terra.

**Effect:**
- Files from completed tasks: entry found, transferred as before
- Files from cancelled/crashed tasks: entry exists but `log_task.task_id IS NULL`,
  filtered out. No "not found" warning. File is not transferred.
- Files with no entry at all (ACQ early-write failed AND XDF split failed): "not
  found" warning still fires — this is the bug-detection canary we want to keep.

**Files:** `neurobooth-terra/neurobooth_terra/dataflow.py`

---

## What this removes

The entire video filename threading pipeline added for #659:

| Component | File | Status |
|---|---|---|
| RecordingFiles buffering by fname | session_controller.py:641-648 | **Remove** |
| fname-keyed pop on TaskCompletion | session_controller.py:630-634 | **Remove** |
| task_video_files dict on SessionState | session_controller.py:279 | **Remove** |
| video_files param on on_task_finished | session_controller.py:90 | **Remove** |
| video_files param on stop_lsl_recording | session_controller.py:478 | **Remove** |
| video_files in postpone_xdf_split | split_xdf.py:213,222 | **Remove** |
| video_files JSON in backlog format | split_xdf.py:222-224 | **Remove** |
| video_files parsing in postprocess | split_xdf.py:247-248 | **Remove** |
| video_files param on split_sens_files | split_xdf.py:28 | **Remove** |
| video_files param on parse_xdf | split_xdf.py:62 | **Remove** |
| DeviceData.video_files field | split_xdf.py:54 | **Remove** |
| RecordingFiles send from DeviceManager | lsl_streamer.py:287-290 | **Remove** |
| RecordingFiles send from EyeTracker | server_stm.py:376-381 | **Remove** |
| RecordingFiles send from calibration | eye_tracker_calibrate.py:23-26 | **Remove** |
| video_files in GUI task_finished | gui.py:516 | **Remove** |

## Critique

### Correctness

The current system is fragile because file registration depends on a long,
multi-machine, partially-deferred pipeline. A break anywhere in the chain means
files exist without entries. The proposed design writes the entry on the same
machine that creates the file, at the same time. The only dependency is the
database being reachable — which it must be for the session to function. If the
database write fails, the XDF split pipeline still creates the entry as a fallback.

### Risk: Removing recently-added code

Steps 4 removes work from three recent commits (4fba312, b52164c8, 6ccbe04b). This
is a deliberate architectural shift: the video filename tracking responsibility moves
from CTR (fragile threading) to ACQ (direct write at creation time). The old code
becomes unnecessary, not broken. Tests from those commits should be updated or
replaced, not silently deleted.

### Risk: Backlog format change

The backlog file format changes from `{xdf_path},{task_id},{log_task_id},{video_json}`
to `{xdf_path},{task_id},{log_task_id}`. Existing backlog files with the old format
would fail to parse. Mitigation: drain the backlog (run post-processing) before
deploying, or add a version check that handles both formats.

### Risk: UPDATE-or-INSERT in log_to_database

The new `log_to_database` tries UPDATE first, falls back to INSERT. If the UPDATE
matches (early row exists), the `ARRAY[hdf5] || sensor_file_path` prepend works
correctly. If no early row exists, the INSERT creates one with just the HDF5 path
(no video files) — same as the current behavior when video_files is empty. This is
acceptable: it means the early write failed AND the old threading pipeline was also
removed. The "not found" canary in the copy script would catch this.

### Risk: Duplicate sensor_file_path entries

If post-processing runs twice on the same XDF (e.g., after a retry), the
`ARRAY[hdf5] || sensor_file_path` prepend would add the HDF5 path again. Mitigation:
check if `sensor_file_path` already contains the HDF5 basename before prepending, or
use the unique index + ON CONFLICT approach from the earlier plan version.

### Risk: Unique index

The UPDATE-or-INSERT approach does NOT require a unique index (it uses WHERE, not
ON CONFLICT). However, a unique index on `(log_task_id, device_id, sensor_id)` would
still be beneficial for data integrity and would enable switching to ON CONFLICT
UPSERT later. Check for duplicates before adding it.

### Risk: ACQ database connection

ACQ already has a database connection for message polling (server_acq.py:62). The
early write uses a separate short-lived connection. If the database is temporarily
unreachable, the `try/except` catches the error and the session continues. The XDF
split creates the entry later as a fallback.

### Risk: Rolling deployment

New fields on `StartRecording` and `TransitionRecording` are Optional with defaults.
Old ACQ ignores `log_task_id` — no early write happens, XDF split creates entries as
before (the INSERT fallback handles this). Old STM doesn't send `log_task_id` — new
ACQ receives `None`, skips early write. Fully compatible in both directions.

However: the video_files pipeline removal (step 4) is NOT backward compatible. If
new CTR runs without the RecordingFiles handler but old ACQ still sends them, the
messages are simply ignored — harmless. If new XDF split runs without video_files
but old backlog entries have them, parsing needs to handle both formats. Deploy
order: ACQ first (adds early writes), then STM (adds log_task_id threading), then
CTR (removes old pipeline), then drain old backlog entries.

### Risk: Orphaned log_task rows

Pre-created `log_task` rows for cancelled tasks have `task_id = NULL`. These
accumulate over time. They're harmless — most queries filter by `task_id`.

### What the copy script filter catches

| Scenario | log_task.task_id | log_sensor_file | Copy action |
|---|---|---|---|
| Normal completion | set | yes, timing filled | transfer |
| User abort ('q') | set | yes, timing filled | transfer |
| Cancel before _perform_task | NULL | yes, no timing | **skip** |
| Crash before _perform_task | NULL | yes, no timing | **skip** |
| Bug: entry never created | -- | missing | **warn** (canary) |
| Old code (no early write) | set | yes (from XDF split) | transfer |

## Files changed

| File | Repo | Change |
|---|---|---|
| `server_stm.py` | neurobooth-os | Pre-create log_task; pass log_task_id; EyeTracker registration; remove RecordingFiles sends |
| `stm_session.py` | neurobooth-os | Add `next_log_task_id` field |
| `messages.py` | neurobooth-os | Add Optional `log_task_id` to StartRecording, TransitionRecording |
| `lsl_streamer.py` | neurobooth-os | Accept `log_task_id`, write log_sensor_file; remove RecordingFiles send |
| `server_acq.py` | neurobooth-os | Pass `log_task_id` from messages to DeviceManager |
| `split_xdf.py` | neurobooth-os | UPDATE-or-INSERT in log_to_database; remove video_files params |
| `session_controller.py` | neurobooth-os | Remove RecordingFiles handler, video_files threading |
| `gui.py` | neurobooth-os | Remove video_files from task_finished handler |
| `headless_listener.py` | neurobooth-os | Remove video_files from on_task_finished |
| `eye_tracker_calibrate.py` | neurobooth-os | Remove RecordingFiles send |
| `dataflow.py` | neurobooth-terra | Add JOIN filter in `copy_files` |

## Database schema

**No schema changes required.** The UPDATE-or-INSERT pattern in step 5 uses a
WHERE clause, not ON CONFLICT:

```python
cursor.execute("""
    UPDATE log_sensor_file SET ...
    WHERE log_task_id = %s AND device_id = %s AND sensor_id = %s
""", ...)
if cursor.rowcount == 0:
    # INSERT fallback
```

This works with the existing schema. If pre-existing duplicate rows exist
(verified: 248 duplicate groups in old data), the UPDATE touches all matching
rows with the same timing data — harmless. No deduplication or unique index
needed.

**Note on dual-sensor devices:** Intel cameras and Mbients have two sensors
(rgb/depth, acc/gyr) sharing a `device_id` but with different `sensor_id`
values. Their `sensor_file_path` arrays look duplicated but the rows are
distinct because `sensor_id` differs. The UPDATE WHERE clause includes
`sensor_id`, so these are correctly handled as separate entries.

## Deploy order

1. Drain existing XDF backlog (run post-processing)
2. Deploy ACQ changes (early writes begin)
3. Deploy STM changes (log_task_id threading begins)
4. Deploy CTR changes (old pipeline removed)
5. Deploy terra copy script change

## Verification

1. **Unit test:** Mock DeviceManager, verify `log_sensor_file` rows created after
   `start_recording_devices` with correct device_id, sensor_ids, file paths
2. **Unit test:** Verify UPDATE-or-INSERT in `log_to_database` — updates timing on
   existing rows, INSERTs when no early row exists, prepends HDF5 correctly
3. **Unit test:** Verify duplicate HDF5 prepend protection (idempotent re-runs)
4. **Integration test:** Run a session, cancel mid-transition, verify:
   - `log_sensor_file` rows exist for the cancelled task (with NULL timing)
   - `log_task.task_id IS NULL` for the cancelled task
   - Copy script produces no "not found" warnings
   - Copy script does NOT transfer the cancelled task's files
5. **Regression:** Run `check_missing_video_files.sql` after a full session — 0 rows
6. **Backlog compat:** Test post-processing with old-format backlog entries
