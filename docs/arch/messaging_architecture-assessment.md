# Messaging Architecture: Design Assessment

An analysis of the strengths and weaknesses of the database-mediated messaging
system described in `messaging_architecture.md`, evaluated against the
requirements of a multi-service neurological data acquisition application.

## Context

Neurobooth-OS coordinates three service types (CTR, STM, ACQ) and multiple
hardware devices during timed clinical data collection sessions. The system must:

1. Reliably start and stop recordings across devices in sync
2. Respond promptly to operator commands (pause, cancel, stop)
3. Handle hardware failures without losing data or hanging
4. Survive abnormal termination without corrupting state

All control-plane messaging flows through a single PostgreSQL `message_queue`
table. Services poll for messages, process them, and post replies.

---

## Strengths

### 1. Simplicity and uniformity

Every message follows one path: INSERT into PostgreSQL, poll with SELECT, mark
read with UPDATE. There is no mix of transports (sockets, shared memory, pipes)
to reason about, debug, or secure. A developer reading any service's main loop
sees the same pattern: `read_next_message` / dispatch / `post_message`.

### 2. Atomic consumption

The CTE in `read_next_message` (metadator.py:222-240) atomically selects the
highest-priority unread row and stamps `time_read = now()` in a single
`UPDATE ... RETURNING` statement. This prevents double-delivery even if two
threads or processes poll the same destination concurrently.

### 3. Durable, inspectable message history

Messages persist in the database after being read. During or after a session, any
message can be queried with standard SQL for debugging or auditing. The
`time_created` and `time_read` columns provide built-in latency measurement for
every message exchange without additional instrumentation.

### 4. Priority preemption

The five-level priority system ensures that `TerminateServerRequest` (100) and
`StopSessionRequest` (100) are always delivered before any queued task or
recording commands (50-75). This is correct for the clinical use case: an operator
pressing Stop must preempt pending work regardless of queue depth.

### 5. Type-safe message bodies

Pydantic models enforce field types and required attributes at construction time.
A `StartRecording` message cannot be posted without `fname`, `task_id`, and
`session_name`. This catches integration errors at the sender rather than at the
receiver, where diagnosis is harder.

### 6. Allowlisted dynamic dispatch

`str_fileid_to_eval` (metadator.py:58-104) validates the module path against a
frozen allowlist before calling `importlib.import_module`. This limits the attack
surface of the `full_msg_type` column to a known set of modules, preventing
arbitrary code execution through crafted database rows.

### 7. Broadcast via multiple rows

Sending a message to multiple destinations (e.g., `PrepareRequest` to STM and
every ACQ) is implemented by posting separate rows. Each destination reads its own
copy independently. This avoids fan-out complexity and lets each receiver process
at its own pace.

### 8. Clean separation of paused-state message handling

STM's paused polling mode uses a dedicated `msg_type IN (...)` filter
(server_stm.py:78-119) that accepts only `ResumeSessionRequest`,
`CancelSessionRequest`, `CalibrationRequest`, and `TerminateServerRequest`.
Normal task commands stay queued and are not lost during a pause.

---

## Weaknesses

### 1. Polling latency is the floor of system responsiveness

Every service polls with a fixed sleep interval:
- **CTR**: 250 ms (gui.py:359)
- **ACQ**: 250 ms (server_acq.py:72)
- **STM main loop**: 1 second (server_stm.py:123)
- **STM paused loop**: 250 ms (server_stm.py:82)
- **Request-confirm waits**: 1 second (server_stm.py:341, 382, 424)

In the critical task-execution path, STM sends `TaskInitialization` to CTR, waits
for `LslRecording`, then sends `StartRecording` to each ACQ and waits for
`RecordingStarted`. Each hop adds up to one full poll interval of latency. With
two ACQ instances, a single task start accumulates up to 3-4 seconds of pure
polling overhead before the task stimulus even begins. The log lines in
`_start_acq` ("Waiting for ACQ to start took: ...") confirm this is an observed
cost in production.

**Impact**: Reduced throughput for short tasks; operator-perceived sluggishness
during session control.

### 2. STM is unreachable during task execution

STM's main loop (server_stm.py:76-172) is single-threaded: it reads one message,
dispatches to a handler, and only reads the next message when the handler returns.
When `_perform_task` is called (line 147), execution does not return to the main
loop until the task stimulus finishes, all recordings are stopped, and the task is
logged. For long-running tasks (e.g., extended cognitive assessments), this can
take 10 minutes or more.

During this time, no messages addressed to STM are read. The priority system is
irrelevant — a `TerminateServerRequest` at priority 100 sits unread in the
database just like a `PauseSessionRequest` at priority 65, because the polling
loop is not running.

The `_perform_task` function does read specific message types in nested wait loops
(`_wait_for_lsl_recording_to_start` polls for `LslRecording`; `_start_acq` polls
for `RecordingStarted`; `stop_acq` polls for `RecordingStopped`), but these
loops filter to a single `msg_type` and ignore everything else.

This creates a concrete operational problem: an operator presses Shut Down during
a long task. The GUI immediately posts `TerminateServerRequest` to both STM and
every ACQ. ACQ reads it on its next 250 ms poll cycle and shuts down. STM does
not read it until the task finishes — potentially many minutes later. In the
meantime, when the task ends and STM calls `stop_acq`, it sends `StopRecording`
to ACQ instances that have already terminated, then waits up to 30 seconds for
`RecordingStopped` replies that will never come.

**Impact**: Operator shutdown and pause commands are silently delayed for the
duration of the running task. ACQ-STM state diverges when ACQ receives a shutdown
that STM has not yet seen. The operator has no indication that the system has not
responded to their command.

### 3. GUI event loop blocked by modal dialogs and synchronous work

The CTR message reader runs on a daemon thread (gui.py:342) and pushes events
into the FreeSimpleGUI event queue via `window.write_event_value()`. However, the
main GUI thread — which processes both user input and these injected events — is
a single `while True` loop calling `window.read(0.5)` (gui.py:650). This loop
blocks in several ways:

**Modal popups freeze all event processing.** The Pause flow is a clear example:
`_pause_tasks` (gui.py:172-194) posts a `PauseSessionRequest` and then
immediately opens `sg.Popup()` with Continue/Stop buttons. While this popup is
open, the main event loop is suspended. If STM finishes the current task and sends
`TaskCompletion` during this time, the message reader thread successfully reads it
and calls `write_event_value("task_finished", ...)`, but the event accumulates in
the queue unprocessed. The same applies to `DeviceInitialization`,
`NewVideoFile`, and any other inbound message. The GUI is effectively deaf to the
system until the operator dismisses the popup.

Similar blocking popups appear in the shutdown confirmation (gui.py:793),
calibration acknowledgment (gui.py:234), eyetracker error (gui.py:881), and
multiple input validation checks (gui.py:684-688).

**Synchronous operations on the main thread.** Several event handlers perform
work that blocks the event loop: `_record_lsl` (gui.py:257-276) calls
`session.start_recording()` synchronously; `handle_task_finished`
(gui.py:929-942) calls `session.stop_recording()` synchronously; and every
`meta.post_message()` call in an event handler performs a blocking database
INSERT.

**Impact**: The GUI becomes unresponsive to operator input during popup dialogs
and LSL operations. Inbound messages from STM and ACQ queue up but are not
processed, delaying the GUI's reaction to task completion, device events, and
error conditions. In a clinical setting, the operator may perceive the system as
hung and take corrective actions (e.g., closing the window) that compound the
problem.

### 4. Inconsistent timeout policies in wait loops (related to #2)

The wait loops that block for confirmations all have timeouts now, but the
durations and the actions taken on timeout vary:

| Wait loop                          | Timeout                | On timeout         |
| ---------------------------------- | ---------------------- | ------------------ |
| `_wait_for_lsl_recording_to_start` | 30 attempts x 1s (30s) | logs and returns   |
| `_start_acq` (RecordingStarted)    | 45s                    | logs partial count |
| `stop_acq` (RecordingStopped)      | 30 attempts x 1s (30s) | logs and returns   |

A timed-out wait does not propagate an error or attempt recovery — STM continues
into the next phase as if the missing replies arrived. If an ACQ service crashed
between receiving `StartRecording` and posting `RecordingStarted`, STM proceeds to
run the task even though only some ACQs are actually recording. Combined with
the absence of a heartbeat (#10), there is no mechanism for the system to detect
or recover from a half-started session — the operator must observe missing data
post-hoc.

**Impact**: Silent partial-failure mode. Sessions can run with missing devices
and the only signal is a log line, with no operator-facing notification.

### 5. No delivery or processing acknowledgment

The system marks a message as read (via `time_read`) the moment it is dequeued
from the database — before the receiving service processes it. If the service
crashes between reading the message and completing the action, the message is
permanently consumed with no record that it was never processed.

For fire-and-forget messages like `StatusMessage`, this is acceptable. For
lifecycle-critical messages like `StartRecording` or `PrepareRequest`, a crash
during processing leaves the system in an inconsistent state with no automatic
recovery path.

**Impact**: Post-crash recovery requires manual intervention; no basis for
automatic retry or dead-letter handling.

### 6. Database round-trip for every message exchange

Each `read_next_message` call executes a CTE query, fetches results into a pandas
DataFrame, commits, closes the cursor, and deserializes JSON. For the common case
of "no message available," this is a full database round-trip that returns an empty
result set. With three services polling at 250 ms each, the system generates
approximately 12 queries per second to the database during idle periods.

The DataFrame construction (`pd.DataFrame(curs.fetchall())` at metadator.py:244)
is particularly wasteful for a query that always returns zero or one rows. The
subsequent `set_axis`, `iloc[0]` extractions, and cursor description access add
overhead that a simple `fetchone()` would avoid.

**Impact**: Unnecessary database load during idle periods; measurable but not
critical overhead per message.

### 7. Binary data through the database (frame previews)

`FramePreviewReply` serializes a camera frame as base64-encoded text in the JSON
body, which is stored in the `message_queue` table and deserialized on read. A
typical camera frame at 1920x1080 in JPEG format is 100-500 KB; base64 encoding
inflates this by 33%. This data passes through JSON serialization, PostgreSQL
storage, and JSON deserialization — a path designed for small control messages.

**Impact**: Frame preview requests add large transient rows to the message table,
increase I/O on the database connection, and contribute to table bloat if the
queue is not promptly cleared.

### 8. Queue cleanup deletes all history without archiving

`clear_msg_queue` (metadator.py:138-152) calls `table.delete_row()` with no
arguments, which deletes every row in the table. This is called at session start
to prevent stale messages from prior sessions. However:

- There is no archival step (the TODO at line 142 acknowledges this)
- If a session terminates abnormally and unread messages remain, the diagnostic
  value of those messages is lost at the next session start
- There is no selective cleanup (e.g., delete only messages older than N minutes
  or only messages from a specific session)

**Impact**: Loss of post-mortem diagnostic data from abnormal terminations.

### 9. String-based message dispatch

All three services dispatch on `message.msg_type` using chains of
`if/elif` string comparisons (server_stm.py:129-161, server_acq.py:77-157,
gui.py:364-431). This pattern:

- Is fragile: a typo in a string literal compiles and runs but silently fails to
  match (e.g., `"RecordingStarted"` vs `"RecordingsStarted"`)
- Requires the handler to cast `message.body` to the correct type manually
- Duplicates the mapping between message types and handlers across three files
- Makes it easy to add a new message type in `messages.py` but forget to handle
  it in one of the services (the `else: raise RuntimeError` in STM catches this
  at runtime, but ACQ just logs and continues)

**Impact**: Maintenance burden; risk of silent message-handling gaps.

### 10. No heartbeat or liveness detection

Services announce themselves at startup with `ServerStarted` but provide no
periodic heartbeat. If STM or ACQ crashes silently (e.g., `os._exit(1)` in the
`finally` block of `main()`), the other services and CTR have no way to detect
the failure except by observing that expected reply messages never arrive.

The operator sees no error message, no status update — just a session that stops
progressing. Combined with the infinite-wait bug in `_start_acq`, this means a
crashed ACQ can leave the system in an undiagnosable hung state.

**Impact**: No fault detection; operator must manually diagnose and restart
failed services.

### 11. Unbounded in-memory frame queues

The webcam and FLIR camera modules use `queue.Queue(0)` (unbounded) to buffer
frames between capture and save threads (webcam.py:43, flir_cam.py:58). If the
disk write thread falls behind the capture thread — due to slow I/O, disk full,
or a brief hang — frames accumulate in memory without limit.

The only monitoring is a log message every 1000 frames when `qsize() > 2`
(webcam.py:158). There is no backpressure mechanism to slow or pause capture,
no maximum queue depth, and no memory usage check.

**Impact**: Potential memory exhaustion during long recording sessions with slow
disk I/O.

### 12. Over-broad exception handling in FLIR capture loop

The FLIR camera's `record()` method catches every `Exception` from
`imgage_proc()` with `except Exception: continue` (flir_cam.py:204-207). This
silently swallows the entire `Exception` hierarchy without logging:

- Timeout exceptions from `GetNextImage(2000)` (expected and harmless)
- Memory errors, type errors, and driver crashes (unexpected and diagnostic)

`KeyboardInterrupt` and `SystemExit` are correctly *not* caught (they inherit
from `BaseException`), so the process can still be stopped. The remaining
problem is that genuine driver or hardware failures produce no log output —
the loop just drops frames.

**Impact**: Hardware or driver failures during recording produce no log output;
the capture loop continues running with dropped frames that are invisible to the
operator.

### 13. Connection proliferation

Each service's main loop holds a long-lived database connection for polling. Each
wait loop (`_wait_for_lsl_recording_to_start`, `_start_acq`, `stop_acq`) opens
an additional connection via `meta.get_database_connection()`. During a single
task execution, STM may hold 3-4 simultaneous database connections, plus the
connections held by CTR and each ACQ instance.

The connections opened in wait loops are closed when the `with` block exits, but
if the wait loop is interrupted by an exception, the connection may leak. There
is no connection pooling.

**Impact**: Elevated connection count on the database server; risk of connection
leaks under error conditions.

### 14. No idempotency guarantees

If a message is accidentally posted twice (e.g., due to a retry after a network
glitch on the INSERT), the receiver will process it twice. There is no
deduplication based on the UUID or any other field. The `uuid` column has a UNIQUE
constraint that would reject an exact duplicate INSERT, but a retry with a new
UUID (as `Message.__init__` generates a fresh `uuid4()` each time) would succeed.

**Impact**: Low risk in practice given the current single-threaded posting
pattern, but no defense against future changes that introduce retries.

---

## Summary

The messaging architecture makes a pragmatic trade-off: it uses PostgreSQL as
both a durable message store and a communication bus, gaining simplicity,
persistence, and auditability at the cost of latency, scalability, and real-time
responsiveness. For a system that runs one session at a time with a small number
of devices, this trade-off is reasonable.

The most consequential weaknesses are not in the choice of transport but in the
application-level protocol built on top of it:

1. **STM is deaf during task execution (#2).** The single-threaded dispatch loop
   stops polling while a task runs. Operator commands (terminate, pause) are
   delayed for the full duration of the task — potentially 10+ minutes. Worse,
   ACQ processes the same terminate command immediately, causing ACQ-STM state
   to diverge.
2. **The GUI blocks on modal dialogs (#3).** While a popup is open, the event
   loop cannot process inbound messages or user input. Events accumulate
   silently and are processed in a burst when the popup closes, which can cause
   out-of-order reactions and operator confusion.
3. **The infinite-wait bug in `_start_acq` (#4)** can deadlock a session with no
   recovery path.
4. **The absence of heartbeats (#10)** means service failures are invisible
   until they cause a downstream timeout — or an infinite hang.
5. **Polling latency compounds across the task-start handshake (#1)**, adding
   observable delay to every task in a session.

Issues #2 and #3 are the primary sources of the operator-visible liveness
problems: the GUI appearing frozen, and the system not responding to shutdown or
pause for extended periods. These are addressable within the current architecture
— STM could poll a dedicated high-priority channel from within task execution
(or run a message-reader thread), and the GUI could replace blocking popups with
non-blocking alternatives or move synchronous work off the main thread.

The remaining issues (timeouts, heartbeats, polling intervals) are also
addressable without replacing the database transport, via consistent timeout
policies, a periodic heartbeat message, and `LISTEN/NOTIFY` for wakeup.
