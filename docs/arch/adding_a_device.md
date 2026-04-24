# Adding a Device to Neurobooth

This guide walks through everything required to add a new data source to a
neurobooth session — a camera, a wearable sensor, a mouse listener, or
anything else that produces a stream of samples. It assumes familiarity with
the codebase layout but not with the device subsystem itself; the relevant
architecture is summarised inline with the step it pertains to.

The device subsystem was designed so that adding a new device touches only
new files. You should not need to edit `DeviceManager`, `lsl_streamer.py`,
`metadator.py`, or any other central dispatcher.

## TL;DR

1. Subclass `Device` in `neurobooth_os/iout/<your_device>.py`, implementing
   `connect`, `start`, `stop`, and declaring the appropriate capability flags.
2. Subclass `DeviceArgs` in `neurobooth_os/iout/stim_param_reader.py` and
   override `device_class()` to return the class from step 1.
3. Add a YAML file to `NB_CONFIG/devices/<device_id>.yml` that points its
   `arg_parser` at your new `DeviceArgs` subclass.
4. Add the device_id to a server's `devices:` list in
   `NB_CONFIG/neurobooth_os_config.yaml`.

## The four artefacts

```
code side (neurobooth-os repo)              config side (NB_CONFIG)
────────────────────────────────            ───────────────────────────────────
neurobooth_os/iout/your_device.py           NB_CONFIG/devices/your_device.yml
  class YourDevice(Device)                    arg_parser: YourDeviceArgs

neurobooth_os/iout/stim_param_reader.py     NB_CONFIG/neurobooth_os_config.yaml
  class YourDeviceArgs(DeviceArgs)            acquisition[N].devices: [..., your_device]
```

The Python side defines *how* the device behaves and what shape its config
takes. The YAML side defines *which* devices exist in a given deployment and
*which machine* runs each one.

## Step 1: Write the Device subclass

Every device inherits from `Device` (in `neurobooth_os/iout/device.py`), which
is an `abc.ABC` with three abstract methods: `connect`, `start`, and `stop`.
Forgetting any of the three is a `TypeError` at construction time — which
fails loud and early, rather than during a live session.

```python
from neurobooth_os.iout.device import Device, DeviceCapability, DeviceState

class YourDevice(Device):
    capabilities = DeviceCapability.STREAM

    def __init__(self, device_args):
        super().__init__(device_args)
        # store device_args, initialise non-hardware state

    def connect(self) -> None:
        # open the hardware handle, create the LSL outlet
        self.outlet = ...
        self.state = DeviceState.CONNECTED

    def start(self, filename: Optional[str] = None) -> List[str]:
        # begin acquisition; return a list of created file basenames
        # (empty list for pure streaming devices)
        self.streaming = True
        self.state = DeviceState.STARTED
        return []

    def stop(self) -> None:
        self.streaming = False
        self.state = DeviceState.STOPPED
```

### The lifecycle

A device progresses through these stages:

```
  CREATED → CONFIGURED → CONNECTED → STARTED → STOPPED → DISCONNECTED
     │                                                        ▲
     │                       close()                          │
     └────────────────────────────────────────────────────────┘
```

| Stage          | Method                 | Default                         |
|----------------|------------------------|---------------------------------|
| `CREATED`      | `__init__`             | Sets common attrs from `DeviceArgs` |
| `CONFIGURED`   | `configure()`          | No-op                           |
| `CONNECTED`    | `connect()`            | **Abstract — must override**    |
| `STARTED`      | `start(filename)`      | **Abstract — must override**    |
| `STOPPED`      | `stop()`               | **Abstract — must override**    |
| `DISCONNECTED` | `disconnect()`         | No-op                           |

`start(filename)` serves two device categories with one signature:
streaming devices (mouse, mic, Mbient) ignore the filename; recording devices
(cameras, EyeLink) use it as the output path and raise `ValueError` if called
without one.

`Device` tracks two external-facing state fields:

- `self.state: DeviceState` — coarse lifecycle state visible to `DeviceManager`.
- `self.streaming: bool` — whether the device is actively producing data.
  Used by `DeviceManager.reconnect_streams()` and the default `close()`.

### Capability flags

`DeviceCapability` is a `Flag` enum. Each subclass declares its capabilities
as a bitwise OR:

```python
capabilities = (
    DeviceCapability.RECORD
    | DeviceCapability.RECORD_PER_TASK
    | DeviceCapability.CAMERA_PREVIEW
)
```

`DeviceManager` uses these flags — not `isinstance` checks — to decide which
devices participate in each operation.

| Flag               | Meaning                                                       |
|--------------------|---------------------------------------------------------------|
| `STREAM`           | Continuously streams to LSL (mouse, microphone, Mbient).      |
| `RECORD`           | Writes to a file; `start(filename)` is required.              |
| `RECORD_PER_TASK`  | Recording is driven by the per-task lifecycle (cameras).       |
| `CAMERA_PREVIEW`   | Supports `frame_preview()`; appears in the operator preview UI. |
| `WEARABLE`         | BLE/wireless; connection may drop and be re-established.       |
| `CALIBRATABLE`     | Supports calibration (EyeLink).                                |
| `RESETTABLE`       | Participates in the operator-triggered reset.                  |

A safe default: forgetting to set `capabilities` on a subclass leaves it at
`DeviceCapability(0)`, so the device is simply not matched by any query.

### Optional lifecycle hooks

Beyond the three abstract methods, `Device` exposes a few hooks with no-op
defaults. Override only the ones you need:

| Hook                          | Override when…                                                            |
|-------------------------------|---------------------------------------------------------------------------|
| `bring_up(context)`           | Your device's startup sequence differs from "connect, then start if streaming". |
| `configure()`                 | Your device needs a separate parameter-application step before `connect`. |
| `ensure_stopped(timeout)`     | `stop()` is asynchronous (e.g. a recording thread you need to join).      |
| `disconnect()`                | You need to release a handle or terminate a helper library.               |
| `close()`                     | The default (`stop()` then `disconnect()`) doesn't cover your teardown.   |
| `frame_preview()`             | You declared `CAMERA_PREVIEW` in `capabilities`.                          |
| `on_task_reconnect()`         | You declared `WEARABLE` and need to re-attach before each task.           |
| `on_session_reset()`          | You declared `RESETTABLE` and participate in the operator Reset UI.       |

### When to override `bring_up`

`DeviceManager` brings each device up by calling `device.bring_up(context)`.
The default runs `connect()` and — for pure streaming devices (`STREAM` but
not `RECORD`) — also `start()`. That covers most devices.

Override `bring_up` when:

- **Startup may fail non-exceptionally.** Return `None` to tell
  `DeviceManager` to skip the device rather than register a broken instance.
  `Mbient` and `IPhone` do this when their handshake fails.
  ```python
  def bring_up(self, context):
      if not self.connect():
          return None
      self.start()
      return self
  ```
- **You need something from the shared context.** `EyeTracker` needs the
  PsychoPy window that only the presentation server has, so its `bring_up`
  pulls it from `context["psychopy_window"]` before calling `connect`.
  ```python
  def bring_up(self, context):
      self.win = context["psychopy_window"]
      self.connect()
      return self
  ```

The context dict is assembled by `DeviceManager.create_streams` and contains
whatever shared resources the presentation server has to offer. Today it has
one key, `"psychopy_window"`; add more if your device needs them.

## Step 2: Write the DeviceArgs subclass

`DeviceArgs` is a Pydantic model that validates the YAML entry and binds the
device to its concrete class. Every subclass must override `device_class()`
with a lazy import of the `Device` class you wrote in step 1. The lazy import
keeps acquisition servers from loading code they don't need (e.g. an ACQ
node does not import the EyeLink driver).

```python
class YourDeviceArgs(DeviceArgs):
    # any device-specific Pydantic fields go here

    @classmethod
    def device_class(cls) -> Type["Device"]:
        from neurobooth_os.iout.your_device import YourDevice
        return YourDevice
```

If your device has no device-specific fields (like `MouseDeviceArgs`), the
subclass body is just the classmethod.

### Environment-specific fields

Some deployment-specific values — a MAC address, a serial number, a microphone
name — shouldn't live in the device YAML because they differ per machine.
They go in `NB_CONFIG/environment.yml` under `ENV_devices.<device_id>` and the
`DeviceArgs.__init__` pulls them out into a flat kwarg. For example,
`MbientDeviceArgs`:

```python
class MbientDeviceArgs(DeviceArgs):
    sensor_array: List[MbientSensorArgs] = []
    mac: str                                    # required; filled from ENV_devices

    def __init__(self, **kwargs):
        my_id = kwargs.get('device_id')
        kwargs['mac'] = kwargs['ENV_devices'][my_id]['mac']
        super().__init__(**kwargs)

    @classmethod
    def device_class(cls) -> Type["Device"]:
        from neurobooth_os.iout.mbient import Mbient
        return Mbient
```

The base `DeviceArgs.__init__` already handles `device_sn` this way, so
device-specific `__init__` overrides are only needed for other env fields.

## Step 3: Add the device YAML

Create `NB_CONFIG/devices/<device_id>.yml`. A minimal example (Mouse):

```yaml
device_id: Mouse
device_name: Mouse
wearable_bool: false
sensor_ids:
  - Mouse
arg_parser: iout.stim_param_reader.py::MouseDeviceArgs()
```

Key fields:

- `device_id` — globally unique across all devices in all environments.
- `arg_parser` — `iout.stim_param_reader.py::<YourDeviceArgs>()`. The runner
  uses this string to instantiate the Pydantic model.
- `sensor_ids` — list of sensor IDs, each of which must have its own YAML in
  `NB_CONFIG/sensors/`. Even devices with no hardware sensor parameters
  (like Mouse) declare a sensor so the database schema has something to join
  against.
- `device_make`, `device_model`, `device_firmware`, `device_name` — logged
  only; nothing reads them at runtime.

If your device has env-specific values (MAC, serial, etc.), add them to
`NB_CONFIG/environment.yml`:

```yaml
ENV_devices:
  your_device:
    mac: "XX:XX:XX:XX:XX:XX"
```

## Step 4: Assign the device to a server

`NB_CONFIG/neurobooth_os_config.yaml` lists which devices each physical
machine runs. Add your `device_id` to the appropriate server's `devices:`
list:

```yaml
acquisition:
  - machine: acq-prod
    devices:
      - Intel_D455_1
      - FLIR_blackfly_1
      - your_device             # ← here
```

Most devices go on an acquisition server. EyeLink and Mouse are the only ones
that currently run on the presentation server. The control server has no
devices.

`DeviceManager` reads this list at startup (`SERVER_ASSIGNMENTS` in
`lsl_streamer.py`), and each server brings up only the devices assigned to it.

## Worked example: `MouseStream`

The simplest real device in the codebase. All four artefacts together:

**`neurobooth_os/iout/mouse_tracker.py`:**

```python
class MouseStream(Device):
    capabilities = DeviceCapability.STREAM

    def __init__(self, device_args: DeviceArgs) -> None:
        super().__init__(device_args)
        self._device_args = device_args

    def connect(self) -> None:
        self._info_stream = set_stream_description(...)
        self.outlet = StreamOutlet(self._info_stream)
        post_message(Request(source="MouseStream", destination="CTR",
                             body=DeviceInitialization(...)))
        self.state = DeviceState.CONNECTED

    def start(self, filename: Optional[str] = None) -> List[str]:
        self.streaming = True
        self.state = DeviceState.STARTED
        self._create_listener()
        self.listener.start()
        return []

    def stop(self) -> None:
        if self.streaming:
            self.streaming = False
            self.state = DeviceState.STOPPED
            self.listener.stop()
```

**`neurobooth_os/iout/stim_param_reader.py`:**

```python
class MouseDeviceArgs(DeviceArgs):
    @classmethod
    def device_class(cls) -> Type["Device"]:
        from neurobooth_os.iout.mouse_tracker import MouseStream
        return MouseStream
```

**`NB_CONFIG/devices/Mouse.yml`:**

```yaml
device_id: Mouse
device_name: Mouse
wearable_bool: false
sensor_ids:
  - Mouse
arg_parser: iout.stim_param_reader.py::MouseDeviceArgs()
```

**`NB_CONFIG/neurobooth_os_config.yaml` (fragment):**

```yaml
presentation:
  machine: stm-prod
  devices:
    - Eyelink_1
    - Mouse
```

No `bring_up` override — the default (connect + start, because `STREAM`
without `RECORD`) is exactly what MouseStream wants. No capability beyond
`STREAM`. That's the whole device.

## Testing

`neurobooth_os/iout/mock_device.py` provides `MockStreamDevice` and
`MockRecordingDevice` — minimal Device subclasses that let you exercise the
base-class lifecycle and `DeviceManager` dispatch without any hardware.

- `tests/pytest/test_device_lifecycle.py` covers the base-class contract:
  state transitions, `close()` idempotency, capability queries.
- `tests/pytest/test_device_pluggable.py` covers `bring_up`, lifecycle hooks,
  capability-gated `DeviceManager` methods, and the `DeviceArgs.device_class()`
  wiring of every concrete device.

Follow the patterns there when writing tests for your device:

- If you can stub hardware access, write an integration test that drives the
  full lifecycle.
- Otherwise, at minimum, add a `test_device_pluggable.TestDeviceArgsClassRegistry`
  entry that asserts your `DeviceArgs` subclass resolves to your concrete
  `Device` class — it's one line and catches wiring mistakes on every change.

## Reference

### Current device catalog

| Device           | Class             | Capabilities                                              |
|------------------|-------------------|-----------------------------------------------------------|
| Mouse            | `MouseStream`     | `STREAM`                                                   |
| Microphone       | `MicStream`       | `STREAM`                                                   |
| Mbient           | `Mbient`          | `STREAM \| WEARABLE \| RESETTABLE`                         |
| FLIR camera      | `VidRec_Flir`     | `RECORD \| RECORD_PER_TASK \| CAMERA_PREVIEW`              |
| Webcam           | `VidRec_Webcam`   | `RECORD \| RECORD_PER_TASK \| CAMERA_PREVIEW`              |
| Intel RealSense  | `VidRec_Intel`    | `RECORD \| RECORD_PER_TASK`                                |
| iPhone           | `IPhone`          | `RECORD \| RECORD_PER_TASK \| CAMERA_PREVIEW`              |
| EyeLink tracker  | `EyeTracker`      | `RECORD \| CALIBRATABLE`                                   |
| Marker stream    | `MarkerStreamDevice` | `STREAM`                                                |

### How `DeviceManager` dispatches

`DeviceManager` (in `lsl_streamer.py`) is device-agnostic. The code paths you'll
touch indirectly:

- **`create_streams(win, task_params)`** — iterates the unique `DeviceArgs`
  across all tasks for the session, instantiates each via
  `device_args.instance_device_class()(device_args)`, and calls `bring_up`.
- **`start_recording_devices`** / **`stop_recording_devices`** — operate on
  devices with `RECORD_PER_TASK` in parallel.
- **`reconnect_for_task`** — calls `on_task_reconnect()` on every Device-backed
  stream before each task.
- **`reset_devices`** — calls `on_session_reset()` on devices that declare
  `RESETTABLE`; returns a dict for the operator UI.
- **`camera_frame_preview(device_id)`** — checks the `CAMERA_PREVIEW` capability
  and delegates to `frame_preview()`.
- **`reconnect_streams`** — for the post-task restart; skips devices with
  `RECORD_PER_TASK` (they're restarted per task instead).
- **`close_streams`** — calls `close()` on every Device at shutdown.

### Key source files

| File                                      | Contents                                                |
|-------------------------------------------|---------------------------------------------------------|
| `neurobooth_os/iout/device.py`            | `Device`, `DeviceCapability`, `DeviceState`, `CameraPreviewException` |
| `neurobooth_os/iout/stim_param_reader.py` | `DeviceArgs` and every subclass                         |
| `neurobooth_os/iout/lsl_streamer.py`      | `DeviceManager`                                         |
| `neurobooth_os/iout/mock_device.py`       | Mock implementations for testing                        |
| `tests/pytest/test_device_lifecycle.py`   | Base-class lifecycle tests                              |
| `tests/pytest/test_device_pluggable.py`   | `bring_up`, hooks, capability dispatch, registry tests  |

## Known open items

- **Marker stream is presentation-node-only.** `DeviceManager.create_streams`
  still hard-codes the marker stream at the presentation node instead of
  flowing it through a YAML like every other device. If you're curious or
  want to pick it up, see the tracking issue for
  [pluggable-device cleanup](https://github.com/neurobooth/neurobooth-os/issues/708).
