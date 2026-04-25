 # Wang Production Deployment: System Diagram

## Physical Machines

```
+-----------------------------------------------------------------------------+
|                     WANG LAB LOCAL NETWORK (192.168.100.x)                   |
|                                                                             |
|  +----------------------------------+  +----------------------------------+|
|  |     CTR Machine (Control)        |  |    ACQ Machine (Acquisition)      ||
|  |     User: CTR                    |  |    User: ACQ                      ||
|  |     Local: C:/neurobooth/        |  |    Local: D:/neurobooth/          ||
|  |                                  |  |                                   ||
|  |  +----------------------------+  |  |  +-----------------------------+  ||
|  |  | gui.py (Operator GUI)      |  |  |  | server_acq.py (ACQ_0)      |  ||
|  |  |  - Session orchestration   |  |  |  |  Process with threads:     |  ||
|  |  |  - LSL recording -> XDF    |  |  |  |  - Main (message loop)     |  ||
|  |  |  - Remote server launch    |  |  |  |  - DeviceManager threads   |  ||
|  |  |    (via WMI)               |  |  |  |  - SystemResourceLogger    |  ||
|  |  |  - Data transfer (robo-    |  |  |  |                             |  ||
|  |  |    copy to Z: drive)       |  |  |  |  Devices:                   |  ||
|  |  |                            |  |  |  |   Intel_D455_1 [037522..]   |  ||
|  |  |  No devices                |  |  |  |   Intel_D455_2 [036322..]   |  ||
|  |  +----------------------------+  |  |  |   Intel_D455_3 [037322..]   |  ||
|  |                                  |  |  |   FLIR_blackfly [205228..]  |  ||
|  +----------------------------------+  |  |   IPhone_dev_1 (WiFi)       |  ||
|                                        |  |   Mbient_BK_1 [F0:2C..]    |  ||
|  +----------------------------------+  |  |   Mbient_LH_2 [E8:95..]    |  ||
|  |  STM Machine (Presentation)      |  |  |   Mbient_RH_2 [C7:94..]    |  ||
|  |  User: STM                       |  |  |   Mic_Yeti (USB audio)      |  ||
|  |  Local: C:/neurobooth/           |  |  +-----------------------------+  ||
|  |                                  |  |                                   ||
|  |  +----------------------------+  |  +----------------------------------+|
|  |  | server_stm.py              |  |                                      |
|  |  |  Process with threads:     |  |  +----------------------------------+|
|  |  |  - Main (PsychoPy + msgs)  |  |  |      Database Server             ||
|  |  |  - SystemResourceLogger    |  |  |      Host: 192.168.100.1         ||
|  |  |  - 230-245 Hz refresh      |  |  |      Port: 5432 (PostgreSQL)     ||
|  |  |                            |  |  |      DB: neurobooth               ||
|  |  |  Device: Eyelink_1         |  |  |      User: neuroboother           ||
|  |  |    IP: 192.168.100.15      |  |  |                                   ||
|  |  |    1000 Hz eye tracking    |  |  |  Tables:                          ||
|  |  +----------------------------+  |  |   message_queue (control plane)   ||
|  |                                  |  |   log_session                     ||
|  |  +----------------------------+  |  |   log_task                        ||
|  |  | server_acq.py (ACQ_1)     |  |  |   log_sensor_file                ||
|  |  |  Separate process          |  |  |   log_application                ||
|  |  |  with threads:             |  |  |   log_system_resource            ||
|  |  |  - Main (message loop)     |  |  |   log_task_param                 ||
|  |  |  - DeviceManager threads   |  |  |   log_device_param               ||
|  |  |  - SystemResourceLogger    |  |  |                                   ||
|  |  |                            |  |  +----------------------------------+|
|  |  |  Devices:                  |  |                                      |
|  |  |   Mouse (pynput)           |  |                                      |
|  |  |   Mbient_LF_2 [DA:B0..]   |  |                                      |
|  |  |   Mbient_RF_2 [E5:F6..]   |  |                                      |
|  |  +----------------------------+  |                                      |
|  |                                  |                                      |
|  +----------------------------------+                                      |
|                                                                             |
+--------------------------------------+--------------------------------------+
                                       |
                                SSH Tunnel via
                         neurodoor.nmr.mgh.harvard.edu
                           (SSH user: sp1022)
                                       |
                       +---------------v---------------+
                       |    Remote Network (MGH/HMS)   |
                       |                               |
                       |  Z: drive (SMB share)         |
                       |   Z:/data/                    |
                       |    +-- XDF files              |
                       |    +-- HDF5 files             |
                       |    +-- Video files            |
                       |                               |
                       |  Dropbox (Video Library)      |
                       |   Videos_to_present/          |
                       |    +-- Task instruction videos|
                       |                               |
                       +-------------------------------+
```

## Control Plane: Message Flow

All inter-service coordination goes through the PostgreSQL `message_queue` table. There are no direct socket connections between machines.

```
                    ┌─────────────────────────────────┐
                    │     PostgreSQL message_queue     │
                    │   (priority-ordered, read-once)  │
                    └──┬──────────┬──────────┬─────────┘
                       │          │          │
              ┌────────▼──┐  ┌───▼────┐  ┌──▼──────────┐
              │    CTR     │  │  STM   │  │ ACQ_0/ACQ_1 │
              └────────────┘  └────────┘  └─────────────┘

Session Lifecycle:

  CTR ──PrepareRequest──────────────────────→ STM, ACQ_0, ACQ_1
  CTR ←─SessionPrepared─────────────────────── STM, ACQ_0, ACQ_1

  CTR ──CreateTasksRequest──────────────────→ STM
  CTR ←─TasksCreated────────────────────────── STM

  For each task:
  ┌─────────────────────────────────────────────────────────────┐
  │ CTR ──PerformTaskRequest────────────────→ STM               │
  │ CTR ←─TaskInitialization─────────────────── STM             │
  │ CTR ──LslRecording (confirm)────────────→ STM               │
  │              STM ──StartRecording────────→ ACQ_0, ACQ_1     │
  │              STM ←─RecordingStarted──────── ACQ_0, ACQ_1    │
  │                                                             │
  │              ... task runs on STM (PsychoPy) ...            │
  │                                                             │
  │              STM ──StopRecording─────────→ ACQ_0, ACQ_1     │
  │              STM ←─RecordingStopped──────── ACQ_0, ACQ_1    │
  │ CTR ←─TaskCompletion─────────────────────── STM             │
  └─────────────────────────────────────────────────────────────┘

  CTR ──TasksFinished───────────────────────→ STM
  CTR ──TerminateServerRequest──────────────→ STM, ACQ_0, ACQ_1
```

## Data Plane: Sensor Streams (LSL)

All sensor data flows via Lab Streaming Layer (LSL) over the local network. CTR records all streams into a single XDF file per task.

```
  ACQ Machine                        STM Machine               CTR Machine
  ═══════════                        ═══════════               ═══════════

  Intel_D455_1 ──30Hz───┐            Eyelink_1 ──1000Hz──┐
  Intel_D455_2 ──30Hz───┤            Marker ─────event────┤
  Intel_D455_3 ──30Hz───┤                                 │
  FLIR_blackfly ─30Hz───┤     ACQ_1 (on STM machine):    │
  IPhone_dev_1 ──30Hz───┤            Mouse ──────50Hz─────┤
  Mbient_BK_1 ──100Hz───┤            Mbient_LF_2 ─100Hz──┤    ┌──────────┐
  Mbient_LH_2 ──100Hz───┼──LSL──────→Mbient_RF_2 ─100Hz──┼───→│ CTR      │
  Mbient_RH_2 ──100Hz───┤                                │    │ records  │
  Mic_Yeti ────48kHz────┘                                 │    │ all to   │
                                                          └───→│ XDF file │
                                                               └──────────┘
```

## Data Storage and Post-Processing Pipeline

```
  During Session:
  ═══════════════

  ACQ local disk (D:/)          STM local disk (C:/)        CTR local disk (C:/)
  ┌─────────────────┐           ┌─────────────────┐         ┌─────────────────┐
  │ Intel .bag files│           │ Eyelink .edf    │         │ session.xdf     │
  │ FLIR video      │           │ Mouse data      │         │ (all LSL streams│
  │ iPhone data     │           │ Mbient LF/RF    │         │  synchronized)  │
  │ Mbient BK/LH/RH│           │                 │         │                 │
  │ Mic audio       │           │                 │         │                 │
  └────────┬────────┘           └────────┬────────┘         └────────┬────────┘
           │                             │                           │
           └──────────── robocopy ───────┴───────────────────────────┘
                              │
                              ▼
                    Z:/data/<session_folder>/
                    ┌────────────────────────┐
                    │ Raw session data       │
                    │ ├ *.xdf                │
                    │ ├ *.bag (Intel)        │
                    │ ├ *.edf (Eyelink)      │
                    │ ├ *.mp4/.mov (video)   │
                    │ └ sensor data files    │
                    └───────────┬────────────┘
                                │
                      split_xdf.py (async)
                                │
                                ▼
                    ┌────────────────────────┐
                    │ Per-device HDF5 files  │      ┌──────────────────┐
                    │ ├ device_data (timeseries)──→│ log_sensor_file  │
                    │ ├ marker_data (events) │      │ table (metadata) │
                    │ └ video_file refs      │      └──────────────────┘
                    └────────────────────────┘
```

## Device Connection Summary

| Device | Machine | Connection | Sample Rate | Output |
|:--|:--|:--|:--|:--|
| Intel_D455_1/2/3 | ACQ | USB 3.0 | 30 Hz RGB+D | .bag files |
| FLIR_blackfly_1 | ACQ | USB 3.0 | ~30 Hz | video (queue→compress→write) |
| IPhone_dev_1 | ACQ | WiFi | ~30 Hz | streamed frames |
| Mbient_BK/LH/RH | ACQ | BLE | 100 Hz 6-axis IMU | LSL → XDF → HDF5 |
| Mic_Yeti | ACQ | USB audio | 48 kHz | LSL → XDF → HDF5 |
| Eyelink_1 | STM | Ethernet (192.168.100.15) | 1000 Hz | .edf + LSL → XDF |
| Mouse | STM (ACQ_1) | USB/pynput | ~50 Hz event | LSL → XDF → HDF5 |
| Mbient_LF/RF | STM (ACQ_1) | BLE | 100 Hz 6-axis IMU | LSL → XDF → HDF5 |

## Key Observations for Performance Analysis

1. **All control messages transit the database** — message_queue polling adds latency to every task transition. Each StartRecording/StopRecording requires a DB round-trip from STM to each ACQ, plus the response.

2. **STM runs 2 processes** that share RAM and CPU: server_stm.py (presentation + Eyelink, with SystemResourceLogger as a background thread) and server_acq.py ACQ_1 (Mouse + foot Mbients, also with its own SystemResourceLogger thread). Each process's SystemResourceLogger thread writes system metrics to `log_system_resource` every 10 seconds.

3. **ACQ handles 9 devices** including 3 USB3 cameras, a FLIR with background compression, 3 BLE Mbients, an iPhone over WiFi, and a USB mic. Peak RAM during recording can reach 51 GB.

4. **The Eyelink's 1000 Hz stream** produces the most data per second and requires PsychoPy window access for calibration — this is why it must be on STM and why STM's Eyelink operations are the bottleneck.

5. **Data transfer happens after session completion** via robocopy to Z: drive. This is network I/O that doesn't affect inter-task timing.
