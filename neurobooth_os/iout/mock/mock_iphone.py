"""In-process mock of the iPhone device.

``MockIPhone`` overrides :meth:`IPhone._handshake` to install a
queue-backed in-process transport (:class:`_MockIPhoneTransport`)
instead of opening a real ``USBMux`` socket.  The state-machine
bookkeeping in ``_send_packet`` / ``_get_packet`` /
``_process_received_message`` runs unchanged; the transport simulates
the iOS app by consuming outgoing packets and queueing the appropriate
responses.

When the controller sends ``@START``, the transport spawns a daemon
thread that emits ``@INPROGRESSTIMESTAMP`` messages at the configured
FPS until ``@STOP`` is sent.  ``frame_preview()`` returns a canned
labeled PNG without touching the camera.
"""

from __future__ import annotations

import json
import logging
import socket
import struct
import threading
import time
from typing import List, Optional

import cv2
import numpy as np

from neurobooth_os.iout.iphone import (
    CONFIG,
    IPhone,
    IPhoneListeningThread,
    IPhonePanic,
    MessageTag,
)


_PREVIEW_WIDTH = 320
_PREVIEW_HEIGHT = 240


def _build_canned_preview_bytes() -> bytes:
    """Build a labeled PNG used as the canned ``@PREVIEW`` response.

    Returns a real PNG so the GUI's ``len(image) < 100`` short-circuit
    in ``handle_frame_preview_reply`` doesn't fire — the operator sees
    a clearly-labeled placeholder rather than ``ERROR: Unable to
    preview (None)``.
    """
    img = np.full(
        (_PREVIEW_HEIGHT, _PREVIEW_WIDTH, 3), 40, dtype=np.uint8)
    cv2.putText(
        img,
        "MOCK iPhone",
        (40, 130),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    rc, encoded = cv2.imencode(".png", img)
    return encoded.tobytes() if rc else b""


_CANNED_PREVIEW_BYTES = _build_canned_preview_bytes()


class _MockIPhoneTransport:
    """Socket-like in-process transport that simulates iPhone app responses.

    Implements the subset of :class:`socket.socket` used by ``IPhone``:
    ``send`` / ``recv`` / ``settimeout`` / ``close``.

    Each outgoing packet is parsed; the message type drives a small
    table of canned responses that get queued for the listener thread to
    pick up.  A separate daemon thread injects
    ``@INPROGRESSTIMESTAMP`` messages between ``@STARTTIMESTAMP`` and
    ``@STOPTIMESTAMP`` to mirror the real recording-progress stream.
    """

    def __init__(self, fps: int = 30, logger: Optional[logging.Logger] = None) -> None:
        self._inbound: List[bytes] = []
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._timeout: Optional[float] = None
        self._closed = False
        self._fps = max(int(fps), 1)
        self._frame_counter = 0
        self._stream_thread: Optional[threading.Thread] = None
        self._stop_streaming = threading.Event()
        self.logger = logger

    # ------------------------------------------------------------------
    # socket-like interface
    # ------------------------------------------------------------------
    def send(self, data: bytes) -> int:
        if len(data) < 16:
            return len(data)
        _version, _type, tag, _payload_size = struct.unpack("!IIII", data[:16])
        if tag == MessageTag.NORMAL_MESSAGE:
            try:
                msg = IPhone._json_unwrap(data[16:])
                self._handle_outgoing(msg)
            except Exception:
                if self.logger is not None:
                    self.logger.exception(
                        "MockIPhoneTransport: failed to parse outgoing packet")
        return len(data)

    def recv(self, n: int) -> bytes:
        with self._cond:
            deadline = (
                time.monotonic() + self._timeout
                if self._timeout is not None
                else None
            )
            while True:
                if self._inbound:
                    head = self._inbound[0]
                    if len(head) >= n:
                        chunk = head[:n]
                        if len(head) == n:
                            self._inbound.pop(0)
                        else:
                            self._inbound[0] = head[n:]
                        return chunk
                    # Defensive: real packets are injected whole, so
                    # this branch should not fire via the IPhone path.
                    self._inbound.pop(0)
                    return head
                if self._closed:
                    return b""
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise socket.timeout("recv timeout")
                    self._cond.wait(remaining)
                else:
                    self._cond.wait()

    def settimeout(self, t: Optional[float]) -> None:
        self._timeout = t

    def close(self) -> None:
        self._stop_streaming.set()
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        if self._stream_thread is not None and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=1.0)
        self._stream_thread = None

    # ------------------------------------------------------------------
    # phone-side simulator
    # ------------------------------------------------------------------
    def _handle_outgoing(self, msg: dict) -> None:
        msg_type = msg.get("MessageType", "")
        if msg_type == "@STANDBY":
            self._inject_message("@READY")
        elif msg_type == "@START":
            # @STARTTIMESTAMP first, then begin the synthetic stream.
            # Order matters: IPhone's state machine requires @STARTTIMESTAMP
            # to land before any @INPROGRESSTIMESTAMP.
            self._inject_message(
                "@STARTTIMESTAMP", timestamp=self._frame_timestamp())
            self._begin_streaming()
        elif msg_type == "@STOP":
            self._end_streaming()
            self._inject_message(
                "@STOPTIMESTAMP", timestamp=self._frame_timestamp())
        elif msg_type == "@PREVIEW":
            self._inject_preview()
        elif msg_type == "@DUMPALL":
            # No files on the mock; drive the empty-list / error path.
            self._inject_message("@ERROR", message="No files on mock device")
        # @DUMP / @DUMPSUCCESS / @DISCONNECT — no responses required.

    def _inject_message(
        self,
        msg_type: str,
        timestamp: str = "",
        message: str = "",
    ) -> None:
        msg = {
            "MessageType": msg_type,
            "SessionID": "",
            "TimeStamp": timestamp,
            "Message": message,
        }
        payload = ("####" + json.dumps(msg)).encode("utf-8")
        header = struct.pack(
            "!IIII", IPhone.VERSION, IPhone.TYPE_MESSAGE, 0, len(payload))
        with self._cond:
            self._inbound.append(header + payload)
            self._cond.notify_all()

    def _inject_preview(self) -> None:
        png = _CANNED_PREVIEW_BYTES
        header = struct.pack(
            "!IIII",
            IPhone.VERSION,
            IPhone.TYPE_MESSAGE,
            int(MessageTag.FRAME_PREVIEW),
            len(png),
        )
        with self._cond:
            self._inbound.append(header + png)
            self._cond.notify_all()

    def _begin_streaming(self) -> None:
        self._stop_streaming.clear()
        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            name="MockIPhone-stream",
            daemon=True,
        )
        self._stream_thread.start()

    def _end_streaming(self) -> None:
        self._stop_streaming.set()
        if self._stream_thread is not None:
            self._stream_thread.join(timeout=1.0)
            self._stream_thread = None

    def _stream_loop(self) -> None:
        period = 1.0 / float(self._fps)
        while not self._stop_streaming.is_set():
            self._frame_counter += 1
            self._inject_message(
                "@INPROGRESSTIMESTAMP",
                timestamp=self._frame_timestamp(),
            )
            self._stop_streaming.wait(period)

    def _frame_timestamp(self) -> str:
        # IPhone._lsl_push_sample uses ``eval`` to parse this back into a
        # dict, so it must be a valid Python literal repr.
        return repr({
            "FrameNumber": self._frame_counter,
            "Timestamp": time.time(),
        })


class MockIPhone(IPhone):
    """Mock iPhone that runs the full state machine without a real device."""

    def _handshake(self, config: CONFIG) -> bool:
        if self._state != "#DISCONNECTED":
            self.logger.error(
                f"iPhone [state={self._state}]: "
                "Mock handshake invoked in inappropriate state.")
            return False
        try:
            fps = int(config.get("FPS", 30))
        except (TypeError, ValueError):
            fps = 30

        self.transport = _MockIPhoneTransport(fps=fps, logger=self.logger)
        try:
            self._update_state("@HANDSHAKE")
        except IPhonePanic as e:
            self.panic(e)
            return False

        self._listen_thread = IPhoneListeningThread(self)
        self._listen_thread.start()
        self.connected = True

        msg_camera_config = {"Message": json.dumps(config)}
        try:
            self._send_and_wait_for_response(
                "@STANDBY",
                msg_contents=msg_camera_config,
                wait_on=list(self.STATE_TRANSITIONS["#STANDBY"].keys()),
            )
            return True
        except IPhonePanic as e:
            self.panic(e)
            return False

    def disconnect(self, join_listener: bool = True) -> bool:
        """Skip the 4-second handshake-cooldown the real iPhone needs."""
        if self._state == "#DISCONNECTED":
            self.logger.debug("MockIPhone: already disconnected")
            return False
        self.logger.debug(
            f"MockIPhone [state={self._state}]: Disconnecting")
        self._update_state("@DISCONNECT")
        self._listen_thread.stop()
        self.transport.close()
        if join_listener:
            self._listen_thread.join(timeout=2)
            # Don't raise on a stuck listener — the mock's transport.close()
            # is reliable enough that this should never happen, and a
            # late teardown shouldn't fail tests.
            if self._listen_thread.is_alive():
                self.logger.warning(
                    "MockIPhone: listener thread did not exit cleanly")
        self.connected = False
        self.streaming = False
        return True
