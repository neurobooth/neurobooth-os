# Testing with Mock Devices

Neurobooth ships mock implementations of every hardware device so you can
run a full session — or write a fast unit test — without an Mbient,
iPhone, or EyeLink connected. The mocks live alongside the real devices
in `neurobooth_os/iout/mock/` and are activated at runtime via an
environment variable or a config field. No YAML changes are required;
the same task collection that runs in production runs against mocks.

For the developer-side architecture (subclass hooks, registry,
adding a mock for a new device), see
[arch/adding_a_device.md → Running with mocks](arch/adding_a_device.md#running-with-mocks).
This document is the operator/tester quick reference.

## Quick start

Pick one or more device-class names — `Mbient`, `IPhone`, `EyeTracker` —
and pass them in `NB_MOCK_DEVICES`:

```bash
# Mock every Mbient in the assigned set, leave iPhone/EyeLink real
NB_MOCK_DEVICES=Mbient python -m neurobooth_os.gui

# Mock several devices at once (whitespace-tolerant)
NB_MOCK_DEVICES="Mbient, IPhone, EyeTracker" python -m neurobooth_os.gui

# Mock everything that has a registered mock
NB_MOCK_DEVICES=all python -m neurobooth_os.gui
```

Targets are device-class names, **not device IDs**, so
`NB_MOCK_DEVICES=Mbient` mocks every Mbient regardless of how many are
assigned.

When at least one mock is active you'll see:

- A `CRITICAL` log entry naming the active targets at GUI startup.
- A red modal dialog listing the active mocks before the main UI opens.

Both are intentional safeguards — a forgotten env var must not
silently corrupt a real recording.

### Persistent fallback (config file)

Mock targets can also live in `neurobooth_os_config.yaml`. The
`mock_devices` entry is a **top-level field** on the config — peer to
`environment`, `screen`, `machines`, `acquisition`, `presentation`,
`control`, and `database`. YAML doesn't care about ordering, but
placing it near `environment:` reads naturally since both flag what
kind of run this is:

```yaml
environment: local
mock_devices: ["Mbient", "IPhone", "EyeTracker"]   # ← here
remote_data_dir: C:/data/
...

screen:
  ...

machines:
  laptop:
    ...

acquisition:
  - machine: laptop
    devices:
      - Mic_Yeti_dev_1
```

Equivalent shorthand forms YAML accepts:

```yaml
mock_devices: [Mbient, IPhone, EyeTracker]   # flow style
mock_devices:                                # block style
  - Mbient
  - IPhone
  - EyeTracker
mock_devices: ["all"]                        # the "all" sentinel
```

Omit the field entirely (or set `mock_devices: null`) for production
envs — that's the default and means no mocks.

The env var **wins** when both are set, so a developer can always
force-enable or force-disable mocks for one run without editing config.
For example, on a laptop env that sets `mock_devices: ["all"]` in the
file, running with `set NB_MOCK_DEVICES=` (empty string) gives a
one-off real-hardware run without touching the YAML.

A laptop dev environment typically sets `mock_devices` in the file;
production environments leave it unset.

## What gets mocked

| Device                 | Mock class           | Activation key in `NB_MOCK_DEVICES` | Hardware bypassed                       |
|------------------------|----------------------|-------------------------------------|-----------------------------------------|
| Mbient wearable        | `MockMbient`         | `Mbient`                            | BLE radio, `mbientlab` SDK              |
| iPhone (camera)        | `MockIPhone`         | `IPhone`                            | USB / `usbmux` / iOS app socket         |
| EyeLink tracker        | `MockEyeTracker`     | `EyeTracker`                        | EyeLink box, `pylink`, `.edf` capture   |
| Yeti microphone        | `MockMicStream`      | `MicStream`                         | `pyaudio`, audio input device           |
| FLIR camera            | `MockVidRec_Flir`    | `VidRec_Flir`                       | `PySpin`, FLIR Spinnaker SDK            |
| Intel RealSense camera | `MockVidRec_Intel`   | `VidRec_Intel`                      | `pyrealsense2`, RealSense SDK           |

The substitution happens inside `DeviceManager.create_streams` at
`device_class()` resolution time — so by the time `bring_up()` runs,
the device instance is already the mock subclass. Operator-facing
behavior (the GUI, log messages, task transitions, file registration)
follows the real lifecycle path.

The "Activation key" column is the literal string `NB_MOCK_DEVICES`
expects (i.e. `real_cls.device_class().__name__`). Examples:

```bash
NB_MOCK_DEVICES="Mbient,IPhone"            # wearables + iphone, real cameras/mic
NB_MOCK_DEVICES="MicStream,VidRec_Flir"    # mic + FLIR cameras, real everything else
NB_MOCK_DEVICES=all                        # every registered mock
```

### What each mock produces

- **`MockMbient`** — a daemon thread emits constant-value accel and gyro
  samples (1g down at rest, zero rotation) at the higher of the
  configured `acc_hz` / `gyro_hz`. The LSL stream shape and cadence
  match the real device; values are not realistic motion.
- **`MockIPhone`** — an in-process queue runs the iOS-app state machine
  end-to-end (`@HANDSHAKE` → `#CONNECTED` → `#STANDBY` → `#READY` →
  `#RECORDING` → ...). A daemon thread emits `@INPROGRESSTIMESTAMP`
  messages between `@STARTTIMESTAMP` and `@STOPTIMESTAMP` at the
  configured FPS so the LSL frame index advances. `frame_preview()`
  returns a canned bytes blob (not a real PNG).
- **`MockEyeTracker`** — a daemon thread emits 13-column synthetic gaze
  samples at `sample_rate` Hz (centred gaze, fixed pupil size). On
  `stop()` it writes a small placeholder `.edf` at the requested path
  so file-cataloguing downstream doesn't choke on a missing file.
  `calibrate()` is a no-op.
- **`MockMicStream`** — a daemon thread pushes zero-filled int16 audio
  chunks to the LSL outlet at the configured `sample_rate /
  sample_chunk_size` rate. The chunk shape matches the real
  microphone's stream; values are silence.
- **`MockVidRec_Flir`** — emits black `320x240x3` frames at the
  configured FPS through the existing save thread, producing a real
  (small) `.avi` file at the requested path via `cv2.VideoWriter`.
  `frame_preview()` returns a real 1-frame PNG (synthesised on the
  fly). Requires `cv2` (opencv-python) — the real path needs it too.
- **`MockVidRec_Intel`** — emits 4-column synthetic LSL samples at the
  configured RGB sample rate. On `stop()` writes a small placeholder
  `.bag` file at the requested path; downstream code finds the file
  but **anything that opens and parses the `.bag`** (e.g. RealSense
  Viewer, `rosbag`-style tooling) will fail because the bytes aren't a
  valid RealSense bag.

### Multiple instances of the same device

Substitution is **per-device-instance**, not per-class. A collection
that assigns five Mbients (`Mbient_BK_1`, `Mbient_LF_2`,
`Mbient_LH_2`, `Mbient_RF_2`, `Mbient_RH_2` — the mvp-30 layout)
gets five independent `MockMbient` instances when
`NB_MOCK_DEVICES=Mbient` is set. Each one:

- Is built via `model_construct(**original_args.model_dump())`, so it
  keeps its own field values (`mac`, `device_name`, `acc_hz`,
  `gyro_hz`) from the YAML.
- Has its own daemon thread emitting samples.
- Pushes to its own LSL outlet under the same `mbient_<dev_name>`
  stream name the real device would have used.

`MockIPhone` and `MockEyeTracker` are typically deployed as a single
instance, but the same per-instance rule applies if your collection
assigns more than one.

## What is *not* mocked

`apply_mock_substitution` only swaps a `DeviceArgs` class if it appears
in `MOCK_REGISTRY`. Six device classes currently have registered mocks:
`MbientDeviceArgs`, `IPhoneDeviceArgs`, `EyelinkDeviceArgs`,
`MicYetiDeviceArgs`, `FlirDeviceArgs`, `IntelDeviceArgs`. Every other
device class in the assigned set passes through to its real
implementation **regardless of `NB_MOCK_DEVICES=all`** — `all` means
"every registered mock target", not "every device".

This matters in two distinct ways:

### Devices that work fine without a mock

- **Mouse** — `MouseDeviceArgs` has no mock and doesn't need one. The
  real `Mouse` class reads OS-level mouse events; on a laptop with a
  trackpad it captures trackpad events. `NB_MOCK_DEVICES=all` does
  **not** replace it.
- **Marker** (`MarkerStreamDevice`) — pure-Python LSL marker producer;
  no hardware to mock.

### Devices that *do* need hardware (and don't have mocks yet)

- **Webcam** (`VidRec_Webcam` in `webcam.py`)

This module still has **eager** top-level SDK imports — the
lazy-import + mock pattern hasn't been extended to it. Two
consequences for a hardware-less laptop:

1. If the SDK isn't installed, `device_class()` resolution raises
   `ImportError` when `DeviceManager.create_streams` tries to load the
   module, and the entire startup fails. The mocks for the other
   devices won't help.
2. If the SDK *is* installed but no real camera/mic is attached, the
   class loads but `bring_up()` fails. It returns `None` and
   `DeviceManager` skips the device — the rest of the session still
   runs.

If your collection requires the webcam, you have three options:

- **(a) Install the SDK even without the hardware.** Lets the module
  import; bring_up will fail and the session continues without that
  stream.
- **(b) Use a reduced collection** that strips out the webcam.
- **(c) Trim the laptop env's `acquisition.devices` list** in
  `neurobooth_os_config.yaml` so no unmocked-and-unavailable devices
  are assigned to begin with.

A full hardware-less mvp-30 run on a laptop now works against `all` —
all of the cameras, the microphone, and the wearables/iPhone/EyeLink
have registered mocks.

## What stays real

Mocks bypass **only** hardware. Everything else runs as in production:

- LSL outlets are real (samples are pushed onto the LSL network).
- The Postgres database is real (mocks call `post_message`,
  `log_sensor_file`, etc.).
- The GUI, PsychoPy window, task code, file registration, XDF split,
  and `DeviceManager` lifecycle are unchanged.

This is intentional: a mocked session exercises the same control plane
and data plumbing as a real one, so most production bugs reproduce on
the mock path.

## Common scenarios

### Single-laptop demo or smoke test

Goal: run a full session GUI-to-XDF without hardware, on the laptop env
config.

```bash
set NB_MOCK_DEVICES=all   # PowerShell: $env:NB_MOCK_DEVICES = "all"
python -m neurobooth_os.gui
```

Confirm:

1. The startup banner names the active mocks.
2. Each *mocked* device's `bring_up` succeeds (logs show
   `Device Manager Substituting MockXxx for Xxx`).
3. A short task runs end-to-end; `log_sensor_file` rows appear with the
   expected `device_id` / `sensor_id` and stub file paths.
4. XDF split succeeds.

This works for any collection whose devices are all in
[What gets mocked](#what-gets-mocked) plus Mouse and Marker (which
need no mock). Collections that assign a webcam need one of the
workarounds in [What is *not* mocked](#what-is-not-mocked).

### Hardware-less unit tests

Each registered mock has a sibling test module under `tests/pytest/`:

- `test_mock_substitution.py` — registry, env-var parsing, lazy imports.
- `test_mock_mbient.py` — bring-up / start / stop / close round-trip.
- `test_mock_iphone.py` — handshake, recording state cycle, frame preview.
- `test_mock_eyetracker.py` — connect, synthetic samples, stub EDF write.
- `test_mock_microphone.py` — connect, start, stop, registry round-trip.
- `test_mock_flir.py` — connect, start, stop, real `.avi` produced, frame preview.
- `test_mock_intel.py` — construct without pyrealsense2, start, stub `.bag` written.

These tests run on a hardware-less laptop without `mbientlab`, `pylink`,
`pyrealsense2`, `PySpin`, or `pyaudio` installed:

```bash
python -m pytest tests/pytest/test_mock_*.py
```

The test files are also a useful reference if you're writing a new test
that needs a device — they show the standard pattern for building a
`MockXxxDeviceArgs` via `model_construct` and silencing `post_message`
so the test doesn't hit the database.

### CI / containerised environments

The Phase 0 import refactor means `mbient.py` and `eyelink_tracker.py`
import cleanly without their hardware SDKs installed (the SDKs are
wrapped in `try / except ImportError`). So a CI image with just `pylsl`
and `psychopy` installed can run the full mock suite.

If your CI environment does not have a configured PsychoPy monitor
center (`monitors.getAllMonitors()` returns an empty list), the
`MockEyeTracker` test fixture passes a `MagicMock` window and the mock
overrides `_resolve_monitor_size` to return canned 1920x1080, so the
tests don't need one.

## Verifying mocks are active

There are several signals depending on what you're checking:

- **GUI** — the red modal at startup lists active targets. No modal
  means no mocks.
- **Logs** — search for `MOCK DEVICES ACTIVE` (CRITICAL) at GUI
  startup, and `Substituting Mock` (INFO) per device in
  `DeviceManager.create_streams`.
- **From Python** — `from neurobooth_os.iout.mock_substitution import
  active_mock_targets; active_mock_targets()` returns the resolved set.
- **Tests** — `MOCK_REGISTRY` (in the same module) lists every
  registered real → mock pairing.

## Pitfalls

- **`all` only mocks what has a registered mock.** Setting
  `NB_MOCK_DEVICES=all` does **not** try to mock the Mouse, Marker,
  Intel camera, FLIR, or microphone — only Mbient / IPhone / EyeLink
  (the three classes in `MOCK_REGISTRY` today). Devices without a
  registered mock pass through to their real implementations
  unchanged, so a working trackpad keeps working under `=all`.
- **Targets are class names, not device IDs.** `NB_MOCK_DEVICES=Mbient`
  mocks every Mbient. `NB_MOCK_DEVICES=Mbient_dev_1` mocks **nothing** —
  there's no class by that name. The env-var-driven path was designed
  this way so a single laptop env config doesn't need a per-device
  YAML override.
- **Empty / unrecognised env var values are silently ignored.**
  `NB_MOCK_DEVICES=` and `NB_MOCK_DEVICES=Foo` both produce zero mocks.
  If you expected a mock and don't see the banner, check the value.
- **`mock_devices` config field is overridden by the env var.** Setting
  `mock_devices: []` in the YAML does not override
  `NB_MOCK_DEVICES=all`. Unset the env var (or `unset NB_MOCK_DEVICES`
  on Unix / `Remove-Item Env:NB_MOCK_DEVICES` on PowerShell) to fall
  back to the config field.
- **Mocks don't simulate hardware failures.** A `MockMbient` doesn't
  drop its connection; `MockIPhone.attempt_reconnect` is a no-op. If
  you're testing recovery code, you'll need to inject the failure
  yourself rather than relying on synthetic flakiness.
- **The mock `.edf` is not a valid EDF file.** Downstream code that
  catalogues sensor files works (the path exists, length is non-zero)
  but anything that opens and parses the EDF will fail. If you need a
  parseable EDF for a downstream test, supply your own fixture.

## Adding a mock for a new device

See [arch/adding_a_device.md → Running with mocks → Adding a mock for
a new device](arch/adding_a_device.md#adding-a-mock-for-a-new-device).
The short version: subclass the real `DeviceArgs`, subclass the real
`Device`, and call `register_mock(real_cls, mock_cls)` at the bottom
of `stim_param_reader.py`.

## See also

- [arch/adding_a_device.md](arch/adding_a_device.md) — full developer
  guide; the "Running with mocks" section is the architectural
  reference.
- [single_machine_testing.md](single_machine_testing.md) — how to run
  the multi-process server stack on one laptop. Predates the mock work
  and references a `test_no_eyelink` collection that's no longer the
  only mock-friendly option — any task collection now runs on a fully
  mocked single-laptop setup.
- `neurobooth_os/iout/mock_substitution.py` — the substitution
  registry and env/config plumbing.
- `neurobooth_os/iout/mock/` — the three mock implementations.
