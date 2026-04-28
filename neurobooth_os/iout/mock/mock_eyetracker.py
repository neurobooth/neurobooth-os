"""Synthetic EyeLink that emits LSL gaze samples without pylink.

Overrides the four hardware hooks on :class:`EyeTracker`:

- ``_resolve_monitor_size`` — returns canned 1920x1080 instead of
  reading PsychoPy's monitor center, which may not be configured on
  laptops/CI.
- ``_connect_tracker`` — skips ``pylink.EyeLink`` and instead installs
  a stub ``tk`` object so inherited code that touches ``self.tk`` (e.g.
  ``close``) works.  Still posts ``DeviceInitialization``.
- ``_begin_native_recording`` — no-op (no EDF, no ``startRecording``).
- ``record`` — synthetic 13-column gaze samples at ``self.sample_rate``
  Hz on a daemon thread.
- ``_receive_data_file`` — writes a tiny stub ``.edf`` so file-cataloguing
  downstream of ``stop()`` doesn't choke on a missing path.
- ``calibrate`` — no-op (the real path uses ``EyeLinkCoreGraphicsPsychoPy``
  which transitively imports pylink).

The mock assumes a real ``psychopy.visual.Window`` for live laptop
sessions, but tolerates a duck-typed window in unit tests because none
of the overridden methods draw to it.
"""

from __future__ import annotations

import threading
import time
from typing import Any, List, Optional, Tuple

from pylsl import local_clock

from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.eyelink_tracker import EyeTracker
from neurobooth_os.iout.metadator import post_message
from neurobooth_os.msg.messages import DeviceInitialization, Request


# Minimal stub bytes for the mock EDF file. Real EDF is a binary EyeLink
# format; downstream consumers (XDF split / log_sensor_file) only need
# the file to exist at the expected path with non-zero length.
_STUB_EDF_BYTES = b"MOCK_EDF_FILE_PLACEHOLDER\n"


class _MockEyelinkHandle:
    """Stub satisfying the ``self.tk`` attribute on inherited paths.

    Production code reaches ``self.tk`` from three places, all of which
    must succeed when the mock is active:

    1. ``EyeTracker.close()`` — calls ``self.tk.close()``.
    2. ``Task_Eyetracker`` wrappers (``sendMessage`` / ``setOfflineMode`` /
       ``startRecording`` / ``sendCommand`` / ``doDriftCorrect`` /
       ``imageBackdrop``) — guarded by ``if self.eye_tracker is not None``,
       so once the mock is wired in they call straight through to ``tk``.
    3. ``Calibrate.present_stimulus`` — drives the EDF file lifecycle by
       hand (``openDataFile`` / ``startRecording`` / ``stopRecording`` /
       ``closeDataFile`` / ``receiveDataFile``) and bypasses the
       ``_receive_data_file`` mock hook, so this stub must materialise
       the calibration ``.edf`` itself.

    All other methods are no-ops.
    """

    def close(self) -> None:
        return None

    def openDataFile(self, filename: str) -> int:
        return 0

    def startRecording(self, *args, **kwargs) -> int:
        return 0

    def stopRecording(self) -> None:
        return None

    def closeDataFile(self) -> None:
        return None

    def receiveDataFile(self, src: str, dst: str) -> int:
        # Calibrate writes the calibration .edf via this path (not via
        # ``_receive_data_file``), so the stub bytes must land at ``dst``
        # so downstream file cataloguing doesn't choke on a missing path.
        try:
            with open(dst, "wb") as fh:
                fh.write(_STUB_EDF_BYTES)
        except OSError:
            pass
        return len(_STUB_EDF_BYTES)

    def sendMessage(self, msg: str) -> None:
        return None

    def setOfflineMode(self) -> None:
        return None

    def sendCommand(self, msg: str) -> int:
        return 0

    def doDriftCorrect(self, *args, **kwargs) -> int:
        return 0

    def imageBackdrop(self, *args, **kwargs) -> int:
        return 0


class MockEyeTracker(EyeTracker):
    """Synthetic EyeLink tracker — no pylink, no EyeLink hardware."""

    # Canned monitor size returned by ``_resolve_monitor_size``.  Kept on
    # the class so tests can override it without touching method bodies.
    MOCK_MONITOR_WIDTH = 1920
    MOCK_MONITOR_HEIGHT = 1080

    def _resolve_monitor_size(self) -> Tuple[int, int]:
        return self.MOCK_MONITOR_WIDTH, self.MOCK_MONITOR_HEIGHT

    def _connect_tracker(self) -> None:
        # Skip pylink.EyeLink; install a stub handle so inherited
        # ``close()`` works without an existence check.
        self.tk = _MockEyelinkHandle()
        body = DeviceInitialization(
            stream_name=self.streamName,
            outlet_id=self.outlet_id,
            device_id=self.device_id,
        )
        msg = Request(source="EyeTracker", destination="CTR", body=body)
        post_message(msg)
        self.logger.info("MockEyeTracker: tracker connection skipped (no pylink)")

    def _begin_native_recording(self) -> None:
        # Real path opens an EDF file on the tracker and arms
        # real-time mode; mock has none of that infrastructure.
        self.logger.info("MockEyeTracker: native recording skipped")

    def record(self) -> None:
        """Emit synthetic 13-column gaze samples until ``self.recording`` clears.

        Column layout matches the real ``record()`` method (see
        ``EyeTracker.connect``):
        R/L gaze (x,y,pupil), target (x,y,distance), resolution (x,y),
        time_edf, time_local.
        """
        period = 1.0 / float(self.sample_rate)
        # Constants for canned samples; the values aren't realistic but
        # downstream code only needs the LSL stream shape and cadence.
        gaze_x = float(self.MOCK_MONITOR_WIDTH) / 2.0
        gaze_y = float(self.MOCK_MONITOR_HEIGHT) / 2.0
        pupil = 1000.0

        self.timestamps_et: List[float] = []
        self.timestamps_local: List[float] = []
        self.paused = False
        self.logger.debug("MockEyeTracker: entering synthetic record loop")
        try:
            while self.recording:
                if self.paused:
                    time.sleep(period)
                    continue
                t_local = local_clock()
                t_edf = t_local * 1000.0  # match real EyeLink ms timestamp
                sample = [
                    gaze_x, gaze_y, pupil,         # right eye
                    gaze_x, gaze_y, pupil,         # left eye
                    0.0, 0.0, 0.0,                 # target x, y, distance
                    1.0, 1.0,                      # ppd x, y
                    t_edf, t_local,
                ]
                self.outlet.push_sample(sample)
                self.timestamps_et.append(t_edf)
                self.timestamps_local.append(t_local)
                time.sleep(period)
        except Exception:
            self.logger.exception("MockEyeTracker: synthetic record loop error")
        finally:
            self.logger.debug("MockEyeTracker: exiting synthetic record loop")

    def _receive_data_file(self) -> None:
        """Write a stub EDF at ``self.filename`` so file paths land on disk."""
        try:
            with open(self.filename, "wb") as fh:
                fh.write(_STUB_EDF_BYTES)
            self.logger.info(
                f"MockEyeTracker: wrote stub EDF at {self.filename}")
        except OSError as e:
            # Best-effort; tests that care can supply a writable path.
            self.logger.warning(
                f"MockEyeTracker: could not write stub EDF at "
                f"{self.filename}: {e}")

    def calibrate(self) -> None:
        # Real path uses EyeLinkCoreGraphicsPsychoPy which transitively
        # imports pylink. Mock skips the entire pylink dance.
        self.logger.info("MockEyeTracker: calibration skipped")
        self.calibrated = True

    def close(self) -> None:
        # Inherited close handles tk.close() (our stub is a no-op) and
        # state transitions; nothing extra needed.
        super().close()
