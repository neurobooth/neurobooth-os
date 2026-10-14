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
| `service_heartbeat` | One row per CTR / STM / ACQ_n process launch, refreshed every ~30 s; `stopped_at` / `exit_code` set on a clean shutdown | `ServiceHeartbeat` thread (`service_monitor.py`) |

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

Exceptions that escape a thread or the main module are logged here at CRITICAL
by the hooks `enable_crash_handler()` installs (`install_exception_hooks()`),
with the message `Uncaught exception in thread <name>; the thread has stopped.`
Without them, a device thread that died printed its traceback only to the
hidden console.

### Service liveness — `service_heartbeat`

A hard crash (access violation, SIGABRT) kills the process before it can write
to `log_application`, so silence there doesn't mean a service is healthy. Each
server's `main()` starts a `ServiceHeartbeat` that upserts its row every 30 s
and marks it stopped, with the exit code, on a clean shutdown. A row that has
stopped beating without a `stopped_at` is a process that died:

```sql
SELECT service_id, server_id, pid, process_start, last_beat, session_id
FROM   service_heartbeat
WHERE  stopped_at IS NULL
  AND  last_beat < now() - interval '2 minutes'
ORDER  BY last_beat DESC;
```

The table is created by `sql/migration/service_heartbeat_v0.96.0.sql`. Without
it the servers still run; the heartbeat logs one warning and keeps retrying.

## On-disk file logs

These live in the **log directory** for each machine (see below). They exist so
that failures *before* or *around* the database logger are never lost.

| File | Purpose | Written by |
| ---- | ------- | ---------- |
| `neurobooth_crash_<service>.log` | `faulthandler` traceback for fatal C-level crashes (segfault / abort). One file per service; before v0.96.0 all services shared `neurobooth_crash.log` | `enable_crash_handler()` |
| `neurobooth_db_log_fallback_<service>.log` | `log_application` records that could not reach the DB, so a DB blip never silently drops logs. Processes that never call `enable_crash_handler()` (e.g. `transfer_data.py`) still use `neurobooth_db_log_fallback.log` | `PostgreSQLHandler` fallback |
| `neurobooth_startup.log` | Last-resort errors before the DB connection exists | `make_fallback_logger()` |
| `<log file>.offset` | Byte offset the startup backfill has read up to | `service_monitor.py` |

A session file/console logger (`make_session_logger_debug()`) is also available
for local debugging.

### Startup backfill

When CTR, STM or ACQ_n starts, `start_service_monitor()` copies into
`log_application` anything its own files gained since the last launch:

- **Crash traces** from `neurobooth_crash_<service>.log`, one ERROR row per
  trace with `device = 'crash_log'`. The current launch's own block is skipped
  and read by the next launch, so a crash is in the database once the service
  has been restarted.
- **DB-fallback records** from `neurobooth_db_log_fallback_<service>.log`.
  WARNING and above are re-logged at their original level, with
  `device = 'db_fallback_log'` and the original timestamp in the message, up to
  200 per launch. Lower levels and anything past the limit are reported as a
  single count.

A backfill failure is logged and never stops the service from starting.

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
  `neurobooth_db_log_fallback_<service>.log`. This replaced an earlier design where a
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
