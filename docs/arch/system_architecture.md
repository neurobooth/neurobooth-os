# System Architecture

Neurobooth runs as a set of cooperating services that communicate through a shared
PostgreSQL message queue. Each service runs on a dedicated (or co-located) Windows
machine and is responsible for a specific role in the data-collection pipeline.

## Services

| Service ID | Role | Typical Machine |
|------------|------|-----------------|
| **CTR** | Control / coordinator. Runs the operator GUI, manages session lifecycle, and records LSL streams. | CTR workstation |
| **STM** | Presentation (stimulus). Drives the PsychoPy window, runs tasks, and controls the Eyelink eye tracker. | STM workstation |
| **ACQ_0** | Primary acquisition. Manages cameras (Intel, FLIR), iPhone, back/hand Mbient wearables, and the Yeti microphone. | ACQ workstation |
| **ACQ_1** | Secondary acquisition (co-located on the STM machine). Manages the foot Mbient wearables and the mouse input stream. | STM workstation |

Any number of acquisition services can exist. They are defined by entries in the
`acquisition` array of the environment config file and are assigned IDs `ACQ_0`,
`ACQ_1`, ... `ACQ_N` based on array index.

## Device Assignment

Devices are assigned to services via the `devices` list in each server's config
entry. The assignment determines which `DeviceManager` instance creates and owns
the LSL streams for those devices.

**Current assignment:**

| Service | Devices |
|---------|---------|
| ACQ_0 | Intel_D455_1..4, FLIR_blackfly_1, IPhone_dev_1, IPhone_dev_stance, Mbient_BK_1, Mbient_LH_2, Mbient_RH_2, Mic_Yeti_dev_1 |
| ACQ_1 | Mouse, Mbient_LF_2, Mbient_RF_2 |
| STM (presentation) | Eyelink_1 |
| CTR (control) | (none) |

**Why Eyelink stays on STM:** The Eyelink eye tracker requires direct access to
the PsychoPy window for calibration rendering and gaze overlay. It must run in the
same process that owns the display.

**Why Mouse and foot Mbients moved to ACQ_1:** These devices have no dependency on
the PsychoPy window. Running them under a separate acquisition service removes
acquisition logic from the presentation server, keeping STM focused on stimulus
delivery. `MouseStream` uses `pynput`, which works independently of PsychoPy.

## Message Routing

Services communicate through a PostgreSQL `message_queue` table. Each message has a
`source`, `destination`, `priority`, and `msg_type`. Services poll for messages
addressed to their service ID.

### Key Message Flows

**Session lifecycle (CTR orchestrates):**

```
CTR --PrepareRequest--> STM, ACQ_0, ACQ_1
STM --SessionPrepared--> CTR
ACQ --SessionPrepared--> CTR
CTR --CreateTasksRequest--> STM
STM --TasksCreated--> CTR
```

**Task execution (STM coordinates recording):**

```
CTR --PerformTaskRequest--> STM
STM --TaskInitialization--> CTR          # "start LSL recording"
CTR --LslRecording--> STM               # "LSL is recording"
STM --StartRecording--> ACQ_0, ACQ_1    # "start device streams"
ACQ --RecordingStarted--> STM           # (one per ACQ)
    ... task runs on STM ...
STM --StopRecording--> ACQ_0, ACQ_1
ACQ --RecordingStopped--> STM
STM --TaskCompletion--> CTR
```

**Mbient reset (during MbientResetPause task):**

```
STM --ResetMbients--> ACQ_0, ACQ_1
ACQ --MbientResetResults--> STM         # (one per ACQ)
```

**Session control:**

```
CTR --PauseSessionRequest--> STM
CTR --ResumeSessionRequest--> STM
CTR --CancelSessionRequest--> STM
CTR --TerminateServerRequest--> STM, ACQ_0, ACQ_1
```

### Message Priority

Messages are read in priority order (highest first), then FIFO within the same
priority level:

| Priority | Messages |
|----------|----------|
| 100 (highest) | TerminateServerRequest, StopSessionRequest |
| 75 | TaskInitialization, LslRecording, TaskCompletion, FramePreviewRequest |
| 65 | PauseSessionRequest, CancelSessionRequest, ResumeSessionRequest |
| 50 (default) | PrepareRequest, SessionPrepared, CreateTasksRequest, StartRecording, etc. |

## Co-located ACQ_1

ACQ_1 runs on the same physical machine as STM but as a separate Windows process
launched via a separate Task Scheduler entry. It uses the same `server_acq.bat`
entry point as ACQ_0. The key config differences:

- **`bat`**: Points to `server_acq.bat` (not `server_stm.bat`)
- **`task_name`**: A unique Task Scheduler name (e.g., `acq-stm-staging`)
- **`name`, `user`, `password`, `local_data_dir`**: Copied from the presentation
  entry since they share the same machine and Windows user account

The service discovers its identity (`ACQ_1`) at startup by matching its config
entry against the `acquisition` array index.

## Configuration Schema

Environment configs live in the `configs` repository under
`environments/<env_name>/neurobooth_os_config.yaml`. The config supports two
formats: a normalized structure (preferred) and a legacy flat structure.

### Normalized format

Machine-level info (user, directories) is defined once in a `machines` dict.
Services reference machines by name and add only service-specific fields.
Passwords are kept in `secrets.yaml`, keyed by machine name (see
`system_configuration.md`).

```yaml
machines:
  acq-prod:
    user: NB_ACQ
    local_data_dir: "E:/neurobooth_data/"
    local_log_dir: "E:/neurobooth_logs/"
  stm-prod:
    user: NB_STM
    local_data_dir: "C:/Users/NB_STM/neurobooth_data/"
    local_log_dir: "C:/Users/NB_STM/neurobooth_logs/"
  ctr-prod:
    user: NB_CTR
    local_data_dir: "C:/Users/NB_CTR/neurobooth_data/"
    local_log_dir: "C:/Users/NB_CTR/neurobooth_logs/"

acquisition:
  - machine: acq-prod
    bat: "%NB_INSTALL%/neurobooth_os/server_acq.bat"
    task_name: acq-prod
    devices: [Intel_D455_1, FLIR_blackfly_1, "..."]
  - machine: stm-prod
    bat: "%NB_INSTALL%/neurobooth_os/server_acq.bat"
    task_name: acq-stm-prod
    devices: [Mouse, Mbient_LF_2, Mbient_RF_2]

presentation:
  machine: stm-prod
  bat: "%NB_INSTALL%/neurobooth_os/server_stm.bat"
  task_name: stm-prod
  devices: [Eyelink_1]

control:
  machine: ctr-prod

database:
  ssh_tunnel: true
  dbname: "..."
  user: "..."
  host: "..."
  port: 5432
  remote_user: "..."
  remote_host: "..."
```

### Legacy flat format

The old format (with `name`, `user`, `password`, `local_data_dir` in every
service entry) is still accepted. It is automatically converted to the
normalized structure at load time. See `docs/arch/config_normalization.md` for
the design rationale.

### Internal model

The config is loaded into a `NeuroboothConfig` Pydantic model at startup via
`config.load_config_by_service_name()`. Internally, machine info is stored in
`MachineSpec` objects and services in `ServiceSpec` objects. Call sites receive
`ResolvedService` instances (from `server_by_name()`, `current_server()`, or
the `acquisition`, `presentation`, `control` properties) that flatten both
layers into a single object with `name`, `user`, `password`, `local_data_dir`,
`local_log_dir`, `bat`, `task_name`, and `devices` attributes.
