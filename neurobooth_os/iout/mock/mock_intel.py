"""Synthetic Intel RealSense camera without pyrealsense2.

Overrides the pyrealsense2-touching hooks on :class:`VidRec_Intel`:

- ``_configure_pipeline`` — no-op (skips the ``rs.config`` /
  ``rs.pipeline`` setup that the real ``__init__`` runs).
- ``_prepare_recording`` — skips ``self.config.enable_record_to_file``;
  records the video filename so ``stop()`` can produce a stub file.
- ``record`` — synthetic frame loop pushes LSL samples at the configured
  RGB sample rate without ever touching ``self.pipeline``.
- ``close`` — skips ``self.config = []`` cleanup that's specific to the
  rs.config object.

After ``stop()``, a small placeholder ``.bag`` file is written at the
expected path so downstream file-cataloguing doesn't choke on a missing
file. The file is **not** a valid RealSense bag — anything that opens
and parses it will fail.
"""

from __future__ import annotations

import os.path as op
import threading
import time
from time import time as wall_time
from typing import List, Optional

from pylsl import local_clock

from neurobooth_os.iout.camera_intel import VidRec_Intel
from neurobooth_os.iout.device import DeviceState


# Placeholder bytes written to the .bag path on stop(). Real bag files
# are binary RealSense capture archives; the mock only needs the path
# to exist so log_sensor_file rows reference a real file.
_STUB_BAG_BYTES = b"MOCK_REALSENSE_BAG_PLACEHOLDER\n"


class MockVidRec_Intel(VidRec_Intel):  # noqa: N801 — match real class casing
    """Mock RealSense camera that emits synthetic LSL samples."""

    def _configure_pipeline(self) -> None:
        # Skip the rs.config / rs.pipeline setup. Inherited code that
        # references ``self.config`` / ``self.pipeline`` is overridden
        # below, so we don't need stubs.
        self.config = None
        self.pipeline = None
        self.logger.info(
            f"MockVidRec_Intel [{self.device_index}]: skipped pyrealsense2 "
            f"pipeline configuration (no hardware)")

    def _prepare_recording(self, name: str) -> None:
        self.name = name
        self.video_filename = f"{name}_intel{self.device_index}.bag"
        # Real path: self.config.enable_record_to_file(self.video_filename).
        # Mock: defer file creation until stop() — see ``_write_stub_bag``.

    def record(self) -> None:
        """Emit synthetic 4-column samples at the configured RGB sample rate."""
        self.frame_counter = 1
        self.logger.debug(
            f"MockVidRec_Intel [{self.device_index}]: synthetic record loop")
        self.toffset = wall_time() - local_clock()

        rate_hz = float(self.device_args.sample_rate()[0])
        period = 1.0 / max(rate_hz, 1.0)

        try:
            while self.recording.is_set():
                self.n = self.frame_counter
                # Match real timestamp shape: pyrealsense2 timestamps are
                # in milliseconds.
                self.tsmp = wall_time() * 1000.0
                try:
                    self.outlet.push_sample(
                        [self.frame_counter, self.n, self.tsmp, wall_time()])
                except Exception as e:
                    self.logger.warning(
                        f"MockVidRec_Intel [{self.device_index}]: "
                        f"reopening closed stream: {e}")
                    self.outlet = self._recreate_outlet()
                    self.outlet.push_sample(
                        [self.frame_counter, self.n, self.tsmp, wall_time()])
                self.frame_counter += 1
                time.sleep(period)
        except Exception:
            self.logger.exception(
                f"MockVidRec_Intel [{self.device_index}]: synthetic record "
                "loop error")
        finally:
            self._write_stub_bag()
            self.record_stopped_flag.set()
            self.logger.debug(
                f"MockVidRec_Intel [{self.device_index}]: synthetic record "
                "loop exited; stub .bag written")

    def _write_stub_bag(self) -> None:
        if self.video_filename is None:
            return
        try:
            with open(self.video_filename, "wb") as fh:
                fh.write(_STUB_BAG_BYTES)
            self.logger.info(
                f"MockVidRec_Intel [{self.device_index}]: wrote stub .bag at "
                f"{self.video_filename}")
        except OSError as e:
            self.logger.warning(
                f"MockVidRec_Intel [{self.device_index}]: could not write stub "
                f".bag at {self.video_filename}: {e}")

    def close(self) -> None:
        self.previewing = False
        self.stop()
        # Real path sets self.config = []; mock has self.config already None.
        self.state = DeviceState.DISCONNECTED
