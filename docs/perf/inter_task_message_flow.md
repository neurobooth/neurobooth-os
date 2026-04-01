# Inter-Task Message Flow

Messages and processing between the end of task N and the start of task N+1.

## Sequence Diagram

```mermaid
sequenceDiagram
    participant ACQ as ACQ (x3)
    participant STM
    participant DB as Message Queue (DB)
    participant CTR as CTR (message reader)
    participant GUI as CTR (GUI event loop)

    Note over STM: task.run() returns

    rect rgb(255, 230, 230)
    Note over STM: PHASE 1: Stop ACQ recording<br/>(STM blocked)

    STM->>DB: StopRecording (to each ACQ)
    ACQ-->>DB: (polls 250ms) reads StopRecording
    Note over ACQ: stops recording devices
    ACQ->>DB: RecordingStopped
    STM-->>DB: (polls 100ms) reads RecordingStopped x3
    Note over STM: stop_acq unblocks
    end

    Note over STM: eyetracker.stop() if applicable

    STM->>DB: TaskCompletion (to CTR, fire-and-forget)

    rect rgb(230, 255, 230)
    Note over STM: PHASE 2: STM post-task work<br/>(no blocking dependency)
    Note over STM: log_task() — DB write
    Note over STM: returns to main loop
    STM-->>DB: (polls 250ms) reads next PerformTaskRequest
    end

    rect rgb(230, 230, 255)
    Note over CTR,GUI: PHASE 2b: CTR handles TaskCompletion<br/>(parallel, no one waits on this)
    CTR-->>DB: (polls 250ms) reads TaskCompletion
    CTR->>GUI: write_event_value("task_finished")
    Note over GUI: window.read() wakes immediately
    Note over GUI: liesl session.stop_recording() — UNKNOWN DURATION
    Note over GUI: starts XDF split thread (non-blocking)
    end

    Note over STM: _perform_task() begins for task N+1
    Note over STM: _get_task_args(), DB logging

    STM->>DB: TaskInitialization (to CTR)

    rect rgb(255, 240, 220)
    Note over STM: PHASE 3: STM blocked on parallel waits

    par Wait for CTR LSL start
        CTR-->>DB: (polls 250ms) reads TaskInitialization
        CTR->>GUI: write_event_value("task_initiated")
        Note over GUI: window.read() wakes immediately
        Note over GUI: liesl session.start_recording() — UNKNOWN DURATION
        GUI->>DB: LslRecording (to STM)
        STM-->>DB: (polls 100ms) reads LslRecording
    and Wait for ACQ recording start
        STM->>DB: StartRecording (to each ACQ)
        ACQ-->>DB: (polls 250ms) reads StartRecording
        Note over ACQ: starts recording devices
        ACQ->>DB: RecordingStarted
        STM-->>DB: (polls 100ms) reads RecordingStarted x3
    end

    Note over STM: Both futures complete, unblocks
    end

    Note over STM: _get_task_instance() — create task, start eyetracker
    Note over STM: task.run() begins for task N+1
```

## Blocking Dependencies

| Blocker | Blocked Service | What It Waits For | Poll Interval | Timeout |
|---------|----------------|-------------------|---------------|---------|
| ACQ stop | **STM** | `RecordingStopped` from each ACQ | 100ms | 30s |
| CTR LSL start | **STM** | `LslRecording` from CTR | 100ms | 30s |
| ACQ start | **STM** | `RecordingStarted` from each ACQ | 100ms | **none** |

STM is the only service that blocks on messages. CTR/GUI processes `TaskCompletion`
asynchronously — nobody waits on it.

## Poll Latencies per Hop

Each message goes through the DB queue. The receiver polls at a fixed interval,
so average pickup latency = interval / 2.

| Hop | Direction | Poll Interval | Avg Latency |
|-----|-----------|---------------|-------------|
| STM main loop | any -> STM | 250ms | ~125ms |
| STM task-critical waits | any -> STM | 100ms | ~50ms |
| ACQ main loop | any -> ACQ | 250ms | ~125ms |
| CTR message reader | any -> CTR | 250ms | ~125ms |
| GUI event loop | CTR thread -> GUI | wakes immediately | ~0ms |

## Critical Path (Minimum Latency)

The shortest possible inter-task time, assuming zero processing:

```
stop_acq:
  STM posts StopRecording                          ~0ms
  ACQ polls and picks up             avg  125ms
  ACQ stops devices                       ???
  ACQ posts RecordingStopped               ~0ms
  STM polls and picks up (x3)       avg   50ms
                                    ───────────
                                    min  175ms + device stop time (x3 ACQs)

STM post-task:
  log_task DB write                       ???
  main loop poll for next msg       avg  125ms
                                    ───────────
                                    min  125ms + DB write

start next task (parallel, take the max):
  Path A — CTR LSL start:
    CTR reader polls                avg  125ms
    GUI event loop wakes             ~0ms  (write_event_value wakes window.read)
    liesl start_recording                ???
    CTR posts LslRecording           ~0ms
    STM polls and picks up          avg   50ms
                                    ───────────
                                    min  175ms + liesl start time

  Path B — ACQ recording start:
    ACQ polls and picks up          avg  125ms
    ACQ starts devices                   ???
    ACQ posts RecordingStarted       ~0ms
    STM polls and picks up (x3)     avg   50ms
                                    ───────────
                                    min  175ms + device start time (x3 ACQs)

  task instance creation                 ???

TOTAL MINIMUM (polls only):         ~475ms
TOTAL WITH UNKNOWNS:                ~475ms + device stop + device start
                                          + liesl stop/start + log_task
                                          + task instance creation
```

The "???" items are what the new timing instrumentation will measure.
