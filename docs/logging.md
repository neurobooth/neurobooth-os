# Neurobooth Logging

An index of everything Neurobooth logs — the database log tables, the on-disk
file logs, and where to look when logging itself misbehaves. Deep-dives for the
two biggest topics live in their own documents:

- **Recording / video file registration** → [arch/video_filename_tracking.md](arch/video_filename_tracking.md)
- **Process crashes & crash dumps** → [booth_crash_dumps.md](booth_crash_dumps.md)

## Database log tables

| Table | What it holds | Written by |
| ----- | ------------- | ---------- |
| `log_application` | Application events and errors — one row per log call (level, message, filename/function/line, traceback, server, session/subject) | The `app` logger via `PostgreSQLHandler` (`log_manager.py`) |
| `log_system_resource` | RAM / swap / CPU / disk / network sampled every ~10 s | `SystemResourceLogger` thread (`log_manager.py`) |
| `log_sensor_file` | One row per recording file — camera video, EyeLink `.edf`, HDF5 path + timing | Each machine at record time; see [video_filename_tracking.md](arch/video_filename_tracking.md) |
| `log_session` / `log_task` / `log_device_param` | Session, task, and per-task device-parameter provenance (what was run, with which settings) | `metadator.py` / `server_stm.py` (`make_new_task_row`, `log_task_params`) |

### Application log — `log_application`

The primary diagnostic log. `make_db_logger()` returns a singleton `app`
logger with a single `PostgreSQLHandler` that owns its own autocommit DB
connection and inserts one row per record. `SESSION_ID` / `SUBJECT_ID` set on
`make_db_logger()` are stamped onto every subsequent row.

Query it directly (e.g. to reconstruct a session's last moments):

```sql
SELECT server_time, server_type, log_level, function, line_no, message
FROM   log_application
WHERE  created_at::date = '<yyyy-mm-dd>'
ORDER  BY server_time;
```

## On-disk file logs

These live in the **log directory** for each machine (see below). They exist so
that failures *before* or *around* the database logger are never lost.

| File | Purpose | Written by |
| ---- | ------- | ---------- |
| `neurobooth_crash.log` | `faulthandler` traceback for fatal C-level crashes (segfault / abort) | `enable_crash_handler()` |
| `neurobooth_db_log_fallback.log` | `log_application` records that could not reach the DB, so a DB blip never silently drops logs | `PostgreSQLHandler` fallback |
| `neurobooth_startup.log` | Last-resort errors before the DB connection exists | `make_fallback_logger()` |

A session file/console logger (`make_session_logger_debug()`) is also available
for local debugging.

### Where log files go

`log_manager._get_log_dir()` resolves the directory in this order:

1. `current_server().local_log_dir` from the machine config, else
2. the `NB_INSTALL` environment variable, else
3. the user's home directory.

On the booth ACQ machine this is `C:\Users\ACQ\nb_os_env\neurobooth_logs` — the
same folder the crash dumps are written to.

## Reliability notes (`PostgreSQLHandler`)

Hard-won behavior worth knowing before touching the DB logging path
(`log_manager.py`):

- **`emit()` never raises.** On a DB error it attempts a **rate-limited
  reconnect** (at most once per 30 s) and one retry, then appends to
  `neurobooth_db_log_fallback.log`. This replaced an earlier design where a
  single DB hiccup silently blinded application logging **process-wide** until a
  restart (fixed in v0.93.4 / PR #823).
- **Short `connect_timeout` (3 s).** A reconnect to a dead DB must not block the
  logging call — and, via the shared handler lock, every other thread that logs.
- **Autocommit only.** Per the handler's own warning, touch `log_application` in
  autocommit mode; `SELECT`s do not block `INSERT`s there.
- **`SystemResourceLogger` wraps each iteration.** One failing `psutil` call
  (e.g. corrupted Windows swap perf counters) is logged and skipped rather than
  killing the whole resource-logging thread silently.

## Crash dumps

The `faulthandler` text log names only Python frames — it cannot identify the
native module (device SDK, BLE library) that actually faulted. For that you need
a memory dump. Capture differs by crash class (SIGABRT abort → ProcDump; native
access violation → WER LocalDumps), and analysis uses `cdb`. See the dedicated
runbook: **[booth_crash_dumps.md](booth_crash_dumps.md)**.
