change# Device Lifecycle

All hardware devices in neurobooth-os inherit from a common `Device` base class
defined in `neurobooth_os/iout/device.py`. This document explains the design,
the Python mechanisms it relies on, and how concrete devices plug in.

## Why a base class?

Before `Device`, each device class invented its own method names and
initialization patterns. `DeviceManager` worked around the inconsistency with
device-specific helpers (`start_cameras`, `get_mbient_streams`, `is_camera`)
that used string matching on device names. Adding a new device type meant
updating those helpers. The base class replaces all of that with a single
interface that `DeviceManager` can call generically.

## Class hierarchy

```
Device (ABC)                        CameraPreviewer (mixin)
  |                                       |
  +-- MouseStream                         |
  +-- MicStream                           |
  +-- Mbient                              |
  +-- VidRec_Intel                        |
  +-- EyeTracker                          |
  +-- VidRec_Flir  --------(also)--------+
  +-- VidRec_Webcam -------(also)--------+
  +-- IPhone  -------------(also)--------+
```

Camera devices inherit from both `Device` and `CameraPreviewer` using Python's
multiple inheritance. `CameraPreviewer` is a mixin that adds the
`frame_preview()` method; it has no `__init__` and no state, so there are no
Method Resolution Order (MRO) conflicts. All device constructors call
`super().__init__(device_args)`, which resolves to `Device.__init__` via
Python's C3 linearization algorithm.

### Method Resolution Order (MRO)

When a class inherits from multiple parents, Python needs a rule for deciding
which parent's method to use. The Method Resolution Order (MRO) is the sequence
Python searches when resolving an attribute or method call. Python computes it
using C3 linearization, which guarantees a consistent left-to-right,
depth-first ordering that respects the inheritance graph.

For a camera device like `VidRec_Flir(Device, CameraPreviewer)`, the MRO is:

```
VidRec_Flir -> Device -> ABC -> CameraPreviewer -> object
```

When `VidRec_Flir.__init__` calls `super().__init__(device_args)`, Python walks
the MRO and finds `Device.__init__` first. `CameraPreviewer` has no `__init__`,
so there is no conflict. If `CameraPreviewer` ever gained an `__init__`, the
`super()` chain would call it automatically -- which is why `super()` is
preferred over explicit `Device.__init__(self, ...)` calls.

You can inspect the MRO of any class at runtime:

```python
>>> VidRec_Flir.__mro__
(<class 'VidRec_Flir'>, <class 'Device'>, <class 'ABC'>, <class 'CameraPreviewer'>, <class 'object'>)
```

## Abstract Base Class (ABC)

`Device` inherits from `abc.ABC` and marks three methods as `@abstractmethod`:

- `connect(self)` -- establish hardware connection and create LSL outlet
- `start(self, filename=None)` -- begin data acquisition
- `stop(self)` -- stop data acquisition

Every device needs all three: a connection to its hardware, a way to start, and
a way to stop. The purpose of ABC is to catch missing implementations early.
Python enforces abstract methods at instantiation time: if a subclass hasn't
overridden every `@abstractmethod`, constructing an instance raises `TypeError`
immediately -- not later when `DeviceManager` tries to call the missing method
during a live session:

```python
class BrokenDevice(Device):
    capabilities = DeviceCapability.STREAM
    def start(self, filename=None):
        ...
    # forgot connect() and stop()

BrokenDevice(args)
# TypeError: Can't instantiate abstract class BrokenDevice
#            with abstract methods connect, stop
```

Without ABC, this would silently create the object and only fail when `stop()`
is called -- possibly mid-recording with hardware active and data flowing. ABC
turns that into a loud, early failure at construction time.

All other lifecycle methods (`configure`, `disconnect`, `ensure_stopped`,
`close`) have concrete no-op defaults and are *not* abstract. Devices override
only the stages they need beyond the three required ones. For example,
`MouseStream` overrides `connect`, `start`, and `stop`, but inherits the
default no-op `configure`, `disconnect`, and `ensure_stopped`.

## Lifecycle stages

A device progresses through these stages in order:

```
  CREATED ──> CONFIGURED ──> CONNECTED ──> STARTED ──> STOPPED ──> DISCONNECTED
     |                                                                  ^
     |                            close()                               |
     +------------------------------------------------------------------+
```

| Stage | Method | Purpose | Default behavior |
|-------|--------|---------|-----------------|
| **CREATED** | `__init__` | Store config, set `outlet_id`, initialize state | Sets common attributes from `DeviceArgs` |
| **CONFIGURED** | `configure()` | Apply device parameters | No-op; sets state |
| **CONNECTED** | `connect()` | Open hardware connection, create LSL outlet | *Abstract -- must override* |
| **STARTED** | `start(filename)` | Begin streaming or recording | *Abstract -- must override* |
| **STOPPED** | `stop()` | Stop streaming or recording | *Abstract -- must override* |
| **DISCONNECTED** | `disconnect()` | Release hardware connection | No-op; sets state |

Additional methods:

- `ensure_stopped(timeout_seconds)` -- Wait for asynchronous stop to complete.
  Cameras override this to join their recording threads; streaming devices
  inherit the no-op default.
- `close()` -- Convenience method that calls `stop()` (if streaming) then
  `disconnect()`. Most devices inherit this; some (like `Mbient`) override it
  to also unsubscribe from data signals.

### State tracking

`Device` tracks state with two fields:

- `self.state: DeviceState` -- an `Enum` with values `CREATED`, `CONFIGURED`,
  `CONNECTED`, `STARTED`, `STOPPED`, `DISCONNECTED`, `ERROR`. This is the
  coarse lifecycle state visible to `DeviceManager`.
- `self.streaming: bool` -- whether the device is actively producing data.
  Used by `DeviceManager.reconnect_streams()` and `Device.close()`.

Some devices have richer internal state (e.g., IPhone has a 12-state machine
for its USB protocol). `DeviceState` is the external-facing state; the
internal state is the device's private concern.

## DeviceCapability flags

Each device class declares its capabilities as a class-level `Flag`:

```python
class DeviceCapability(Flag):
    STREAM          # Continuous LSL streaming (mouse, mic, mbient)
    RECORD          # Records to file; start(filename) required
    CAMERA_PREVIEW  # Supports frame_preview()
    WEARABLE        # BLE/wireless; may disconnect unexpectedly
    CALIBRATABLE    # Supports calibration (eyelink)
```

`Flag` is a Python enum type that supports bitwise combination with `|`:

```python
class VidRec_Flir(Device, CameraPreviewer):
    capabilities = DeviceCapability.RECORD | DeviceCapability.CAMERA_PREVIEW
```

`DeviceManager` uses these flags to query devices generically:

```python
cameras = device_manager.get_devices_with_capability(DeviceCapability.RECORD)
wearables = device_manager.get_devices_with_capability(DeviceCapability.WEARABLE)
```

This replaces the old string-matching pattern (`is_camera("FLIR_...")`) that
required code changes every time a new device type was added.

### Current capability assignments

| Device | Class | Capabilities |
|--------|-------|-------------|
| Mouse | `MouseStream` | `STREAM` |
| Microphone | `MicStream` | `STREAM` |
| Mbient | `Mbient` | `STREAM \| WEARABLE` |
| FLIR camera | `VidRec_Flir` | `RECORD \| CAMERA_PREVIEW` |
| Webcam | `VidRec_Webcam` | `RECORD \| CAMERA_PREVIEW` |
| Intel RealSense | `VidRec_Intel` | `RECORD` |
| iPhone | `IPhone` | `RECORD \| CAMERA_PREVIEW` |
| EyeLink tracker | `EyeTracker` | `RECORD \| CALIBRATABLE` |

## ClassVar for capabilities

The `capabilities` attribute is annotated with `typing.ClassVar`:

```python
capabilities: ClassVar[DeviceCapability] = DeviceCapability(0)
```

`ClassVar` tells type checkers (and developers) that this is a class-level
attribute shared by all instances, not an instance attribute. Each subclass
overrides it with its own flags. The base class default is `DeviceCapability(0)`
(no capabilities), so forgetting to set it on a subclass means the device
won't be matched by any capability query -- a safe default.

## The start(filename) contract

The `start` method accepts an optional `filename` parameter:

```python
@abstractmethod
def start(self, filename: Optional[str] = None) -> None:
```

This unifies two device categories:

- **Streaming devices** (mouse, mic, mbient) ignore the filename. They stream
  data continuously to LSL and don't write files.
- **Recording devices** (cameras, eyelink) require the filename to know where
  to write their output. They raise `ValueError` if called without one.

`DeviceManager` can call `device.start(filename=fname)` on any device without
needing to know which category it belongs to.

## How DeviceManager uses the interface

`DeviceManager` (in `lsl_streamer.py`) manages the collection of device
instances and dispatches lifecycle calls:

**Device creation** -- Factory functions (`start_flir_stream`, etc.) construct
the device, call `connect()`, and optionally call `start()`. The factory
function is resolved from a string in the database config.

**Recording lifecycle** -- `start_recording_devices(filename, task_devices)`
starts all `RECORD`-capable devices in parallel using a thread pool.
`stop_recording_devices(task_devices)` signals stop on all of them, then waits
via `ensure_stopped()`.

**Reconnection** -- `reconnect_streams()` iterates all non-recording devices
and restarts any that have `streaming == False`.

**Shutdown** -- `close_streams()` calls `device.close()` on every `Device`
instance. The default `close()` calls `stop()` then `disconnect()`.

## Known gaps

### Wearable reconnect is not on the Device interface

The `WEARABLE` capability implies the device may disconnect unexpectedly and
supports reconnection. However, there is no `reconnect()` method on `Device`.
Reconnect logic currently lives entirely in `Mbient.attempt_reconnect()` and
`Mbient.task_start_reconnect()`, and `DeviceManager.mbient_reconnect()` calls
those Mbient-specific methods directly.

This works because Mbient is currently the only wearable. If a second wearable
device type is added, `reconnect()` should be promoted to the `Device`
interface (likely as an optional method, similar to `ensure_stopped()`), and
`DeviceManager.mbient_reconnect()` should be generalized to iterate all
`WEARABLE` devices. The same applies to `mbient_reset()` -- board-level reset
may not apply to other wearables, but a generic `reset()` method could be
defined with device-specific implementations.

## Adding a new device

1. Create a class that inherits from `Device` (and `CameraPreviewer` if it
   supports frame previews).
2. Set `capabilities` as a class variable.
3. Override `connect()` to set up hardware and create the LSL outlet.
4. Override `start()` and `stop()`.
5. Override `ensure_stopped()` if stop is asynchronous (e.g., thread-based recording).
6. Write a factory function in `lsl_streamer.py` that constructs the device and
   calls `connect()`.

The device will automatically work with `DeviceManager`'s generic lifecycle
methods. No changes to `DeviceManager` are needed.

## Testing

Mock implementations (`MockStreamDevice`, `MockRecordingDevice`) are provided
in `neurobooth_os/iout/mock_device.py` for testing against the `Device`
interface without hardware. Tests are in `tests/pytest/test_device_lifecycle.py`
and cover state transitions, capability queries, `close()` behavior, and
idempotency.

## Key source files

| File | Contents |
|------|----------|
| `neurobooth_os/iout/device.py` | `Device`, `DeviceCapability`, `DeviceState`, `CameraPreviewer` |
| `neurobooth_os/iout/lsl_streamer.py` | `DeviceManager`, factory functions |
| `neurobooth_os/iout/mock_device.py` | Mock implementations for testing |
| `tests/pytest/test_device_lifecycle.py` | Lifecycle tests |
