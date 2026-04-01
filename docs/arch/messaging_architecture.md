# Messaging Architecture

This document provides an in-depth reference for the database-mediated messaging
system that connects the CTR, STM, and ACQ services. For the broader system
architecture (services, devices, configuration), see `system_architecture.md`.

## Overview

All inter-service communication flows through a shared PostgreSQL
`message_queue` table. Services post messages by inserting rows, and consume
messages by polling for unread rows addressed to their service ID. There are no
direct sockets, RPC calls, or shared-memory channels between services — the
database is the single communication bus.

LSL (Lab Streaming Layer) is used separately for real-time sensor data, but all
*control-plane* coordination uses the message queue.

## Database Schema

Inferred from `metadator.py` (`post_message` and `read_next_message`):

```sql
message_queue (
    id              SERIAL PRIMARY KEY,
    uuid            UUID UNIQUE,
    msg_type        VARCHAR,          -- e.g. 'PrepareRequest'
    full_msg_type   VARCHAR,          -- e.g. 'msg.messages.py::PrepareRequest()'
    source          VARCHAR,          -- e.g. 'CTR', 'STM', 'ACQ_0'
    destination     VARCHAR,          -- e.g. 'STM', 'ACQ_0'
    priority        INTEGER,          -- higher = more urgent
    body            JSONB,            -- serialized MsgBody
    time_created    TIMESTAMP,        -- set by DB on INSERT
    time_read       TIMESTAMP         -- NULL until consumed
)
```

**Read semantics:** A message can only be read once. `read_next_message`
atomically selects the highest-priority unread row for a destination and stamps
`time_read = now()` in the same `UPDATE ... RETURNING` statement.

**Ordering:** `ORDER BY priority DESC, id ASC` — highest priority first, then
FIFO within the same priority level.

## Message Envelope

Every message is wrapped in a `Message` (or its subclass `Request`) defined in
`neurobooth_os/msg/messages.py`:

```python
class Message:
    uuid: str               # auto-generated UUID4
    msg_type: str           # body class name, e.g. 'PrepareRequest'
    source: str             # posting service ID
    destination: str        # target service ID
    priority: int           # from body.priority
    body: MsgBody           # Pydantic model with message payload
```

The `full_msg_type` field is derived at post time:

```python
def full_msg_type(self) -> str:
    module = self.body.module                     # e.g. 'neurobooth_os.msg.messages'
    module = module.replace('neurobooth_os.', '')  # e.g. 'msg.messages'
    return f"{module}.py::{self.body.msg_type}()"  # e.g. 'msg.messages.py::PrepareRequest()'
```

On the read side, `str_fileid_to_eval(full_msg_type)` dynamically imports the
body class so the JSON payload can be deserialized back into the correct Pydantic
model. This is protected by a module allowlist (`_ALLOWED_MESSAGE_MODULES`).

## Priority Levels

Five constants defined in `messages.py`:

| Constant | Value | Used By |
|----------|-------|---------|
| `HIGHEST_PRIORITY` | 100 | `TerminateServerRequest`, `StopSessionRequest` |
| `HIGH_PRIORITY` | 75 | `TaskInitialization`, `TaskCompletion`, `LslRecording`, `RecordingStarted`, `RecordingStopped`, `NoEyetracker`, `NewVideoFile`, `FramePreviewRequest`, `FramePreviewReply` |
| `MEDIUM_HIGH_PRIORITY` | 65 | `PauseSessionRequest`, `ResumeSessionRequest`, `CancelSessionRequest`, `CalibrationRequest`, `MbientResetResults` |
| `MEDIUM_PRIORITY` | 50 | `PrepareRequest`, `SessionPrepared`, `CreateTasksRequest`, `TasksCreated`, `StartRecording`, `StopRecording`, `DeviceInitialization`, `MbientDisconnected`, `ResetMbients`, `StatusMessage`, `ErrorMessage` |
| `LOW_PRIORITY` | 25 | (currently unused) |

The priority system ensures that shutdown and stop commands preempt all other
work, session-control messages (pause/resume/cancel) preempt normal task flow,
and task-lifecycle confirmations are processed before routine status updates.

## Message Types

All message body classes extend `MsgBody` and are defined in
`neurobooth_os/msg/messages.py`.

### Session Lifecycle

| Message | Direction | Priority | Purpose |
|---------|-----------|----------|---------|
| `PrepareRequest` | CTR → STM, ACQ | 50 | Initialize session (subject, collection, study IDs) |
| `SessionPrepared` | STM/ACQ → CTR | 50 | Confirm preparation complete |
| `CreateTasksRequest` | CTR → STM | 50 | Build task objects, load media |
| `TasksCreated` | STM → CTR | 50 | Confirm tasks are ready |
| `TasksFinished` | CTR → STM | 50 | Signal end of session |
| `TerminateServerRequest` | CTR → STM, ACQ | 100 | Shut down server process |

### Task Execution

| Message | Direction | Priority | Purpose |
|---------|-----------|----------|---------|
| `PerformTaskRequest` | CTR → STM | 50 | Execute a specific task |
| `TaskInitialization` | STM → CTR | 75 | Task starting — begin LSL recording |
| `LslRecording` | CTR → STM | 75 | LSL recording is active |
| `StartRecording` | STM → ACQ | 50 | Start device acquisition |
| `RecordingStarted` | ACQ → STM | 75 | Confirm devices are recording |
| `StopRecording` | STM → ACQ | 50 | Stop device acquisition |
| `RecordingStopped` | ACQ → STM | 75 | Confirm devices have stopped |
| `TaskCompletion` | STM → CTR | 75 | Task finished — stop LSL recording |

### Session Control

| Message | Direction | Priority | Purpose |
|---------|-----------|----------|---------|
| `PauseSessionRequest` | CTR → STM | 65 | Pause after current task |
| `ResumeSessionRequest` | CTR → STM | 65 | Resume paused session |
| `CancelSessionRequest` | CTR → STM | 65 | Cancel session |
| `StopSessionRequest` | CTR → STM | 100 | Immediate stop |
| `CalibrationRequest` | CTR → STM | 65 | Trigger eye-tracker calibration |

### Device Events

| Message | Direction | Priority | Purpose |
|---------|-----------|----------|---------|
| `DeviceInitialization` | Device → CTR | 50 | Report device ready with LSL outlet ID |
| `NoEyetracker` | STM → CTR | 75 | Eyelink not found or failed |
| `MbientDisconnected` | Device → CTR | 50 | Mbient wearable lost connection |
| `ResetMbients` | STM → ACQ | 50 | Request Mbient reset |
| `MbientResetResults` | ACQ → STM | 65 | Report reset success/failure per device |
| `NewVideoFile` | Device → CTR | 75 | Camera/marker produced a new file |

### Diagnostics

| Message | Direction | Priority | Purpose |
|---------|-----------|----------|---------|
| `FramePreviewRequest` | CTR → ACQ | 75 | Request a camera frame |
| `FramePreviewReply` | ACQ → CTR | 75 | Return encoded frame bytes |
| `StatusMessage` | Any → CTR | 50 | Informational status text |
| `ErrorMessage` | Any → CTR | 50 | Error notification |

## Message Filtering

`read_next_message(destination, conn, msg_type)` applies different SQL filters
depending on the `msg_type` argument:

### Default (`msg_type=None`)

Used by the main polling loops in all three services:

```sql
msg_type NOT IN ('LslRecording', 'RecordingStarted',
                 'RecordingStopped', 'MbientResetResults')
```

These four types are excluded because they are consumed by dedicated
single-message wait loops during task execution, not by the general dispatcher.

### Paused state (`msg_type='paused_msg_types'`)

Used by `server_stm.py` while the session is paused:

```sql
msg_type IN ('ResumeSessionRequest', 'CancelSessionRequest',
             'CalibrationRequest', 'TerminateServerRequest',
             'MbientResetResults')
```

Only messages meaningful during a pause are processed. Normal task commands are
ignored until the session resumes or is cancelled.

### Specific type (`msg_type='<TypeName>'`)

Used by wait loops that block until a particular confirmation arrives:

```sql
msg_type = %s
```

Examples: STM waits for `'LslRecording'` after sending `TaskInitialization`;
STM waits for `'RecordingStarted'` / `'RecordingStopped'` from each ACQ.

## Producers and Consumers

### Who Posts Messages

| Source | File | Message Types |
|--------|------|---------------|
| CTR (GUI) | `gui.py` | `PrepareRequest`, `CreateTasksRequest`, `PerformTaskRequest`, `PauseSessionRequest`, `ResumeSessionRequest`, `CancelSessionRequest`, `TasksFinished`, `LslRecording`, `FramePreviewRequest`, `TerminateServerRequest`, `CalibrationRequest` |
| STM | `server_stm.py` | `ServerStarted`, `SessionPrepared`, `TasksCreated`, `TaskInitialization`, `TaskCompletion`, `StartRecording`, `StopRecording`, `StatusMessage`, `ErrorMessage` |
| ACQ | `server_acq.py` | `ServerStarted`, `SessionPrepared`, `RecordingStarted`, `RecordingStopped`, `MbientResetResults`, `FramePreviewReply`, `ErrorMessage` |
| Devices | various `iout/*.py` | `DeviceInitialization`, `NoEyetracker`, `MbientDisconnected`, `NewVideoFile`, `StatusMessage` |
| Tasks | `task_basic.py`, `mbient_reset.py` | `StatusMessage`, `ResetMbients` |

### Who Reads Messages

| Destination | File | Polling Mode |
|-------------|------|-------------|
| CTR | `gui.py` (`_start_ctr_msg_reader`) | Default filter (general loop) |
| STM | `server_stm.py` (`run_stm`) | Default filter (main loop), `'paused_msg_types'` (paused), `'LslRecording'` / `'RecordingStarted'` / `'RecordingStopped'` (wait loops) |
| ACQ_N | `server_acq.py` (`run_acq`) | Default filter (main loop) |
| STM | `mbient_reset.py` | `'MbientResetResults'` (task-specific wait) |

## Dynamic Dispatch (`str_fileid_to_eval`)

When a message is read from the database, the `full_msg_type` string
(e.g. `"msg.messages.py::PrepareRequest()"`) is used to reconstruct the body
object:

```python
body_constructor = str_fileid_to_eval(msg_type_full, allowed_modules=_ALLOWED_MESSAGE_MODULES)
msg_body = body_constructor(**body_json)
```

`str_fileid_to_eval` parses the string into a module path and function name,
validates the module against a frozenset allowlist, then calls
`importlib.import_module` and `getattr`. The allowlist prevents arbitrary code
execution if the `full_msg_type` column is tampered with.

The same function is used for other dynamic imports with different allowlists:

| Call Site | Allowlist | Modules Permitted |
|-----------|-----------|-------------------|
| `read_next_message` | `_ALLOWED_MESSAGE_MODULES` | `msg.messages` |
| `_dynamic_parse` (YAML config parsers) | `_ALLOWED_PARSER_MODULES` | `iout.stim_param_reader`, `tasks.MOT.task` |
| `build_task` (task constructors) | `_ALLOWED_TASK_MODULES` | `tasks` (prefix, covers all submodules) |
| `DeviceManager.create_streams` | `_ALLOWED_DEVICE_MODULES` | `iout.lsl_streamer` |

## Message Lifecycle

```
1. CREATE    Sender builds Message(body=SomeMsgBody(...), source=..., destination=...)
                 ↓
2. POST      meta.post_message(msg, conn)
             → INSERT into message_queue (body serialized to JSON)
                 ↓
3. QUEUE     Row sits in DB with time_read = NULL
             → Ordered by (priority DESC, id ASC) for readers
                 ↓
4. READ      meta.read_next_message(destination, conn, msg_type)
             → Atomic SELECT + UPDATE time_read = now()
             → full_msg_type resolved via str_fileid_to_eval()
             → JSON body deserialized into Pydantic model
             → Returns Message object (or None if queue empty)
                 ↓
5. DISPATCH  Service handler switches on msg_type and processes
             → May post reply messages, starting the cycle again
```

## Synchronization Patterns

### Fire-and-Forget

Most messages are posted without blocking. The sender continues immediately
and the receiver picks them up on its next poll cycle. Used for status updates,
device events, and session-control commands.

### Request–Confirm

Several flows require the sender to block until a confirmation arrives.
The sender posts a message, then enters a polling loop calling
`read_next_message` with a specific `msg_type` filter until the expected
reply appears.

**Examples:**
- STM sends `TaskInitialization` → polls for `LslRecording`
- STM sends `StartRecording` → polls for `RecordingStarted` (one per ACQ)
- STM sends `StopRecording` → polls for `RecordingStopped` (one per ACQ)
- STM sends `ResetMbients` → polls for `MbientResetResults`

These loops include timeout handling and abort-key checking to avoid infinite
blocking.

### Broadcast

Some messages are posted to multiple destinations. CTR sends `PrepareRequest`
and `TerminateServerRequest` to both STM and every ACQ by posting separate
rows for each destination.

## Queue Cleanup

`meta.clear_msg_queue(conn)` deletes all rows from `message_queue`. This is
called at session start to clear stale messages from prior sessions that may
have terminated abnormally.

## Key Files

| File | Role |
|------|------|
| `neurobooth_os/msg/messages.py` | All message type definitions (MsgBody subclasses) |
| `neurobooth_os/iout/metadator.py` | `post_message`, `read_next_message`, `str_fileid_to_eval`, allowlists |
| `neurobooth_os/server_stm.py` | STM message handler and synchronization loops |
| `neurobooth_os/server_acq.py` | ACQ message handler |
| `neurobooth_os/gui.py` | CTR message reader and all outbound control messages |
