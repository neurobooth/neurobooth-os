"""Regression tests for IPhone wire-framing payload reassembly (``_get_packet``).

Guards the Wang 2026-06 failure: the ``@DUMPALL`` reply is a single
``NORMAL_MESSAGE`` whose JSON payload (the list of every file on the phone)
grew past what one ``socket.recv()`` returns (~32 KB).  ``_get_packet`` read
that payload with a bare ``recv()``, so a large reply was truncated ->
``json.loads`` raised ``Unterminated string starting at ... char 32714`` ->
the overflow bytes left in the socket were read as the next packet header ->
``Incorrect tag (...) received`` PANIC.

The fix routes the ``NORMAL_MESSAGE`` branch through ``recvall()`` (the same
looping read the binary/file-dump branches already use).  These tests fail
against the bare-``recv`` code and pass against ``recvall``.

Why the existing ``MockIPhone`` lifecycle tests never caught this: the mock
transport returns a whole injected packet from one ``recv(n)``, so the payload
was never split.  ``_ChunkedTransport`` below deliberately fragments ``recv``
to mimic a real TCP socket.
"""

import struct

import pytest

from neurobooth_os.iout import iphone as iphone_mod
from neurobooth_os.iout.iphone import IPhone, MessageTag


class _ChunkedTransport:
    """Socket-like transport whose ``recv()`` returns at most ``chunk`` bytes
    per call, mimicking a real TCP socket that hands back only what has
    currently arrived.  ``settimeout`` / ``close`` are no-ops; ``recv`` past
    the end returns ``b""`` (socket-closed semantics).
    """

    def __init__(self, data: bytes, chunk: int = 4096) -> None:
        self._buf = bytes(data)
        self._pos = 0
        self._chunk = chunk

    def recv(self, n: int) -> bytes:
        if self._pos >= len(self._buf):
            return b""
        take = min(n, self._chunk, len(self._buf) - self._pos)
        out = self._buf[self._pos:self._pos + take]
        self._pos += take
        return out

    def settimeout(self, _t):
        pass

    def close(self):
        pass


def _frame_normal_message(msg: dict) -> bytes:
    """Build a wire packet exactly as the iPhone app does: 16-byte big-endian
    header (version, type, tag=NORMAL_MESSAGE, payload_size) + "####" + JSON.
    """
    payload = IPhone._json_wrap(msg).encode("utf-8")
    header = struct.pack(
        "!IIII",
        IPhone.VERSION,
        IPhone.TYPE_MESSAGE,
        int(MessageTag.NORMAL_MESSAGE),
        len(payload),
    )
    return header + payload


def _large_filelist_message(n_files: int) -> dict:
    """A realistic ``@DUMPALL`` reply: ``Message`` is the list of files on the
    phone, each an entry with a name and base64 MD5 (as the real app sends)."""
    file_list = [
        {
            "file": f"100001_2026-06-25_task{i:04d}_obs_1_IPhone_dev_1-{i}.mov",
            "md5": "Zm9vYmFyYmF6cXV4MDEyMzQ1Njc4OWFiY2RlAA==",
        }
        for i in range(n_files)
    ]
    return {
        "MessageType": "@FILESTODUMP",
        "SessionID": "",
        "TimeStamp": "",
        "Message": file_list,
    }


@pytest.fixture(autouse=True)
def _disable_lsl(monkeypatch):
    # Defensive: keep the device fully offline (no LSL outlets) for the test.
    monkeypatch.setattr(iphone_mod, "DISABLE_LSL", True)


def _make_iphone() -> IPhone:
    # device_args=None is hardware-free -- exactly how dump_iphone_video.py
    # constructs it; Device.__init__ only attaches a logger.
    return IPhone(name="framing_test", enable_timeout_exceptions=True)


def test_get_packet_reassembles_large_filelist_over_32k():
    """A NORMAL_MESSAGE payload larger than a single recv() chunk (and larger
    than the ~32 KB cap that bit Wang) must be reassembled intact."""
    device = _make_iphone()
    msg = _large_filelist_message(2000)
    framed = _frame_normal_message(msg)
    assert len(framed) > 32768, "regression payload must exceed the single-recv cap"

    # chunk << payload forces the multi-recv reassembly path
    device.transport = _ChunkedTransport(framed, chunk=4096)

    payload, _version, _type, tag = device._get_packet()

    assert tag == MessageTag.NORMAL_MESSAGE
    assert payload == msg
    assert len(payload["Message"]) == 2000


def test_get_packet_reassembles_when_split_into_tiny_chunks():
    """Even pathological fragmentation (64-byte reads) must reassemble; this is
    the strongest form of the regression."""
    device = _make_iphone()
    msg = _large_filelist_message(500)
    framed = _frame_normal_message(msg)

    device.transport = _ChunkedTransport(framed, chunk=64)

    payload, _version, _type, tag = device._get_packet()

    assert payload == msg
    assert len(payload["Message"]) == 500


def test_get_packet_small_message_whole_delivery():
    """The common case -- a small NORMAL_MESSAGE delivered in one recv() --
    still works after the fix (recvall's single-iteration fast path)."""
    device = _make_iphone()
    msg = {
        "MessageType": "@READY",
        "SessionID": "",
        "TimeStamp": "",
        "Message": "",
    }
    framed = _frame_normal_message(msg)

    device.transport = _ChunkedTransport(framed, chunk=65536)

    payload, _version, _type, tag = device._get_packet()

    assert tag == MessageTag.NORMAL_MESSAGE
    assert payload == msg
