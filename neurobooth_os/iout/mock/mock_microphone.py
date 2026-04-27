"""Synthetic microphone that emits LSL audio chunks without pyaudio.

Overrides the single hardware hook on :class:`MicStream`
(``_acquire_audio_stream``) plus the streaming method (``stream``) and
the lifecycle methods that touch pyaudio (``stop``, ``disconnect``).

Synthetic samples are produced by a daemon thread that pushes
constant-zero int16 chunks at the configured ``sample_rate /
sample_chunk_size`` rate.  Downstream code only needs the LSL stream
shape and cadence, not realistic audio.
"""

from __future__ import annotations

import threading
import time
from typing import List, Optional

import numpy as np
from pylsl import local_clock

from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.microphone import MicStream


class MockMicStream(MicStream):
    """Mock microphone that emits zero-filled audio chunks on a daemon thread."""

    def _acquire_audio_stream(self) -> None:
        # Skip pyaudio device enumeration and stream open. Inherited
        # ``connect()`` continues to ``_publish_outlet()`` after this.
        self.device_name = f"MockMicrophone-{self._device_args.microphone_name}"
        self.logger.info(
            f"MockMicStream: skipped pyaudio acquire (no hardware); "
            f"reporting device_name={self.device_name}")

    def stream(self) -> None:
        """Emit zero-filled int16 chunks at the configured chunk rate."""
        chunk_period = float(self.CHUNK) / float(self.fps)
        zero_chunk = np.zeros(self.CHUNK, dtype="int16")
        self.last_time = int(local_clock() * 10e3)
        self.logger.debug("MockMicStream: entering synthetic stream loop")
        try:
            while self.streaming:
                tlocal = int(local_clock() * 10e3)
                tdiff = tlocal - self.last_time
                self.last_time = tlocal
                payload = np.hstack((np.array(tdiff), zero_chunk))
                try:
                    self.outlet_audio.push_sample(payload)
                except BaseException:
                    # Match the real stream's recover-on-closed-outlet behaviour.
                    self.logger.debug(
                        "MockMicStream: reopening LSL outlet (was closed)")
                    from pylsl import StreamOutlet
                    self.outlet_audio = StreamOutlet(self._stream_info_audio)
                    self.outlet_audio.push_sample(payload)
                # Wait a chunk's worth of wall-clock time before the next
                # synthetic chunk so the LSL cadence matches the real path.
                time.sleep(chunk_period)
        finally:
            self.stream_on = False
            self.logger.debug("MockMicStream: exiting synthetic stream loop")

    def disconnect(self) -> None:
        """Skip pyaudio teardown; mock has no native handles to release."""
        self.state = DeviceState.DISCONNECTED
