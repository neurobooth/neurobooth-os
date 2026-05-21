"""Tests for the XDF salvage path in ``neurobooth_os.iout.split_xdf``.

Background: LabRecorderCLI segfaults at XDF finalize (#812) leave the
written file with a truncated/corrupt StreamHeader chunk. pyxdf's
``load_xdf`` raises ``xml.etree.ElementTree.ParseError`` reading that
chunk's XML and aborts the whole load, taking down the post-process
split for every other stream in the file. The salvage path enumerates
StreamIds by walking the chunk framing only (no XML parse), then loads
each stream individually so a single broken header skips that stream
instead of losing the whole file.

These tests cover the byte-level chunk walker (``enumerate_stream_ids``)
against hand-crafted XDF bytes. End-to-end ``_load_xdf_with_salvage``
behaviour is exercised in production against the real stuck files; a
synthetic broken XDF that pyxdf can partially parse is non-trivial to
build and not load-bearing here.
"""
from __future__ import annotations

import struct

import pytest

from neurobooth_os.iout.split_xdf import enumerate_stream_ids


# ---- helpers to build synthetic XDF byte strings -----------------------------

def _varlen(size: int) -> bytes:
    """Encode an XDF varlen-int length prefix."""
    if size < 256:
        return bytes([1, size])
    if size < 2**32:
        return bytes([4]) + struct.pack('<I', size)
    return bytes([8]) + struct.pack('<Q', size)


def _chunk(tag: int, stream_id: int = 0, content: bytes = b'') -> bytes:
    """Build a single XDF chunk: <varlen size><tag><stream_id?><content>."""
    body = struct.pack('<H', tag)
    if tag in (2, 3, 4, 6):
        body += struct.pack('<I', stream_id)
    body += content
    return _varlen(len(body)) + body


def _file_header_chunk() -> bytes:
    return _chunk(tag=1, content=b'<?xml version="1.0"?><info><version>1.0</version></info>')


def _stream_header_chunk(stream_id: int, xml: bytes = b'<info></info>') -> bytes:
    return _chunk(tag=2, stream_id=stream_id, content=xml)


def _samples_chunk(stream_id: int, payload: bytes = b'\x00' * 16) -> bytes:
    return _chunk(tag=3, stream_id=stream_id, content=payload)


def _boundary_chunk() -> bytes:
    # 16-byte signature pyxdf recognizes; content beyond that is irrelevant
    # for our walker (we just skip the chunk body).
    sig = bytes([0x43, 0xA5, 0x46, 0xDC, 0xCB, 0xF5, 0x41, 0x0F,
                 0xB3, 0x0E, 0xD5, 0x46, 0x73, 0x83, 0xCB, 0xE4])
    return _chunk(tag=5, content=sig)


# ---- tests ------------------------------------------------------------------

def test_enumerate_finds_all_stream_headers(tmp_path):
    path = tmp_path / 'multi.xdf'
    body = (
        b'XDF:'
        + _file_header_chunk()
        + _stream_header_chunk(1)
        + _stream_header_chunk(42)
        + _samples_chunk(1)
        + _stream_header_chunk(999)
        + _boundary_chunk()
    )
    path.write_bytes(body)
    assert enumerate_stream_ids(str(path)) == [1, 42, 999]


def test_enumerate_ignores_other_chunk_tags(tmp_path):
    """Tag-3 (Samples), tag-4 (ClockOffset), tag-6 (Footer) chunks also
    carry a StreamId field but should not contribute new IDs to the
    enumeration -- only tag-2 (StreamHeader) chunks do."""
    path = tmp_path / 'mixed.xdf'
    body = (
        b'XDF:'
        + _file_header_chunk()
        + _stream_header_chunk(7)
        + _samples_chunk(7)
        + _chunk(tag=4, stream_id=7, content=b'\x00' * 16)  # ClockOffset
        + _chunk(tag=6, stream_id=7, content=b'<info></info>')  # StreamFooter
    )
    path.write_bytes(body)
    assert enumerate_stream_ids(str(path)) == [7]


def test_enumerate_tolerates_corrupt_streamheader_xml(tmp_path):
    """The whole point: a tag-2 chunk whose XML content is garbage still
    has a correctly-framed length prefix and stream_id field, so we can
    enumerate it -- which is what lets the salvage path try to load OTHER
    streams in the file."""
    path = tmp_path / 'broken_xml.xdf'
    garbage_xml = b'<info><name>oops' + b'\x00' * 50  # truncated, unbalanced
    body = (
        b'XDF:'
        + _file_header_chunk()
        + _stream_header_chunk(11)
        + _stream_header_chunk(22, xml=garbage_xml)
        + _stream_header_chunk(33)
    )
    path.write_bytes(body)
    # All three IDs should be discoverable even though stream 22's XML
    # would explode an XML parser.
    assert enumerate_stream_ids(str(path)) == [11, 22, 33]


def test_enumerate_stops_at_truncated_chunk(tmp_path):
    """A file truncated mid-chunk (the smoking-gun shape of a
    LabRecorderCLI crash mid-write) shouldn't raise -- the walker should
    return everything it managed to read and exit cleanly."""
    path = tmp_path / 'truncated.xdf'
    good = b'XDF:' + _file_header_chunk() + _stream_header_chunk(5)
    # Append the START of another StreamHeader chunk but cut it off mid-content
    next_chunk = _stream_header_chunk(99, xml=b'A' * 300)
    truncated = good + next_chunk[: len(next_chunk) - 200]
    path.write_bytes(truncated)
    # The walker reads the length prefix, sees a content length it can't
    # satisfy via f.seek (well, seek can advance past EOF on most platforms
    # but subsequent reads will fail), and exits cleanly. The completed
    # stream 5 is reported; stream 99 may or may not be reported depending
    # on whether seek + the subsequent EOF read combo flagged the chunk
    # before it could record the StreamId.
    ids = enumerate_stream_ids(str(path))
    assert 5 in ids
    # All ids must be ints (no garbage)
    assert all(isinstance(i, int) for i in ids)


def test_enumerate_rejects_non_xdf_file(tmp_path):
    """Files without the XDF magic should raise rather than walk garbage
    bytes (which would otherwise return whatever spurious tag-2 sequences
    happen to align)."""
    path = tmp_path / 'notxdf.bin'
    path.write_bytes(b'GIF89a' + b'\x00' * 100)
    with pytest.raises(ValueError, match='not an XDF file'):
        enumerate_stream_ids(str(path))


def test_enumerate_handles_4byte_varlen_size(tmp_path):
    """Most chunks fit in 1-byte size prefix; large chunks use the 4-byte
    form. Verify the walker handles both."""
    path = tmp_path / 'big_chunk.xdf'
    # 4 KB of fake XML in one StreamHeader chunk -- forces 4-byte varlen prefix
    big_xml = b'<info>' + (b'X' * 4000) + b'</info>'
    body = (
        b'XDF:'
        + _file_header_chunk()
        + _stream_header_chunk(1)
        + _stream_header_chunk(2, xml=big_xml)
        + _stream_header_chunk(3)
    )
    path.write_bytes(body)
    assert enumerate_stream_ids(str(path)) == [1, 2, 3]


def test_enumerate_empty_file(tmp_path):
    """An empty file (no XDF magic) should raise ValueError, not silently
    return an empty list."""
    path = tmp_path / 'empty.xdf'
    path.write_bytes(b'')
    with pytest.raises(ValueError, match='not an XDF file'):
        enumerate_stream_ids(str(path))


def test_enumerate_xdf_with_only_header(tmp_path):
    """An XDF with magic + FileHeader but no streams -- the walker should
    return an empty list, not raise."""
    path = tmp_path / 'header_only.xdf'
    path.write_bytes(b'XDF:' + _file_header_chunk())
    assert enumerate_stream_ids(str(path)) == []
