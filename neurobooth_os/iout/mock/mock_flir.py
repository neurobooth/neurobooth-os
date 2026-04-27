"""Synthetic FLIR camera that writes a real video file without PySpin.

Overrides the PySpin-touching hooks on :class:`VidRec_Flir`:

- ``get_cam`` / ``setup_cam`` — no-ops; install a stub ``self.cam`` so
  inherited methods that reach into ``self.cam`` (record-loop teardown,
  ``close``) don't ``AttributeError``.
- ``imgage_proc`` — returns a synthetic ndarray frame plus a
  monotonic-ish timestamp, in place of ``self.cam.GetNextImage`` +
  ``cv2.demosaicing``.
- ``_prepare_recording`` — skips ``self.cam.BeginAcquisition`` /
  ``AcquisitionResultingFrameRate`` and uses the configured FPS to set
  up the ``cv2.VideoWriter``.
- ``frame_preview`` — skips ``BeginAcquisition`` / ``EndAcquisition``.
- ``close`` — skips ``self.cam.DeInit``.

The synthetic record loop pushes black frames at ``device_args.sample_rate()``
through the existing ``camCaptureVid`` save thread, so a real (small)
.avi file is produced at the requested path — downstream
file-cataloguing finds a non-empty file at the expected location.
"""

from __future__ import annotations

import os.path as op
import threading
import time
from typing import Any, ByteString, List, Optional, Tuple

import cv2
import numpy as np

from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.flir_cam import VidRec_Flir


# Synthetic frame size: small enough that the mock video file stays
# small even over a long task, large enough that downstream tooling
# that opens the .avi finds non-degenerate dimensions.
_MOCK_FRAME_WIDTH = 320
_MOCK_FRAME_HEIGHT = 240


class _MockCamStub:
    """Stand-in for the ``self.cam`` PySpin object on inherited paths.

    The real ``record()`` loop calls ``self.cam.EndAcquisition()`` in its
    ``finally`` clause; the inherited ``close()`` calls ``DeInit``.
    Stubbing both as no-ops keeps inherited code paths working without
    overriding them in the mock.
    """

    def BeginAcquisition(self) -> None:  # noqa: N802 — match PySpin casing
        return None

    def EndAcquisition(self) -> None:  # noqa: N802
        return None

    def DeInit(self) -> None:  # noqa: N802
        return None

    def AcquisitionResultingFrameRate(self) -> float:  # noqa: N802
        # Real method returns the actual frame rate the camera achieves;
        # mock just reports the configured target.
        return 60.0


class MockVidRec_Flir(VidRec_Flir):  # noqa: N801 — match real class casing
    """Mock FLIR camera that writes synthetic video frames at sample_rate."""

    def __init__(self, device_args, **kwargs) -> None:
        super().__init__(device_args, **kwargs)
        self._mock_frame_counter = 0

    def get_cam(self) -> None:
        self.system = None
        self.cam = _MockCamStub()
        self.logger.info("MockVidRec_Flir: skipped PySpin camera acquire")

    def setup_cam(self) -> None:
        self.open = True
        self.logger.info("MockVidRec_Flir: skipped PySpin camera setup")

    def imgage_proc(self) -> Tuple[np.ndarray, int]:  # noqa: N802 — match real spelling
        self._mock_frame_counter += 1
        # Black frame; downstream code only inspects shape / file
        # existence, not pixel content.
        frame = np.zeros(
            (_MOCK_FRAME_HEIGHT, _MOCK_FRAME_WIDTH, 3), dtype=np.uint8)
        # FLIR timestamps are nanoseconds; multiply local clock to mimic.
        tsmp = int(time.time() * 1e9)
        # The real method applies self.fd (frame-decimation) via
        # cv2.resize; preserve that so frame size matches user
        # expectations on downstream paths.
        return cv2.resize(frame, None, fx=self.fd, fy=self.fd), tsmp

    def _prepare_recording(self, name: str = "temp_video") -> None:
        # Skip BeginAcquisition; build the writer directly.
        im, _ = self.imgage_proc()
        self.frameSize = (im.shape[1], im.shape[0])
        self.video_filename = f"{name}_flir.avi"
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.FRAME_RATE_OUT = float(self.device_args.sample_rate())
        self.video_out = cv2.VideoWriter(
            self.video_filename, fourcc, self.FRAME_RATE_OUT, self.frameSize)
        self.streaming = True

    def record(self) -> None:
        """Synthetic record loop: emit black frames at sample_rate FPS."""
        self.logger.debug("MockVidRec_Flir: synthetic record loop started")
        self.recording = True
        self.frame_counter = 0
        self.save_thread = threading.Thread(target=self.camCaptureVid)
        self.save_thread.start()

        period = 1.0 / float(self.device_args.sample_rate())
        self.stamp: List[int] = []
        try:
            while self.recording:
                im, tsmp = self.imgage_proc()
                self.image_queue.put(im)
                self.stamp.append(tsmp)
                try:
                    self.outlet.push_sample([self.frame_counter, tsmp])
                except BaseException:
                    self.logger.debug(
                        "MockVidRec_Flir: reopening LSL outlet (was closed)")
                    self._create_outlet()
                    self.outlet.push_sample([self.frame_counter, tsmp])
                self.frame_counter += 1
                time.sleep(period)
        except Exception:
            self.logger.exception(
                "MockVidRec_Flir: synthetic record loop error")
        finally:
            self.recording = False
            self.save_thread.join()
            self.video_out.release()
            self.logger.debug(
                "MockVidRec_Flir: synthetic record loop exited; video written")

    def frame_preview(self) -> ByteString:
        img, _ = self.imgage_proc()
        rc, encoded = cv2.imencode(".png", img)
        return encoded.tobytes() if rc else b""

    def close(self) -> None:
        self.stop()
        self.open = False
        self.state = DeviceState.DISCONNECTED
