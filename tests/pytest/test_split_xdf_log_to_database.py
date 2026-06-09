"""Tests for ``neurobooth_os.iout.split_xdf.log_to_database``.

Regression coverage for #819: a stream with zero samples (most commonly
Mouse, which only emits samples on movement) is legitimate data, but pre-fix
the per-device loop ran ``timestamps[0]`` unconditionally and raised
IndexError on the empty case. The exception propagated out of
``log_to_database`` before ``conn.commit()`` was reached, rolling back every
device's pending UPDATE/INSERT and leaving the entire task's
``log_sensor_file`` rows empty.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from neurobooth_os.iout.split_xdf import DeviceData, log_to_database


def _mock_conn(rowcount: int = 1) -> MagicMock:
    """Build a mock psycopg2-like connection. Its cursor.execute reports
    ``rowcount`` so the first UPDATE in log_to_database short-circuits and
    we do not need to mock the INSERT fallback path."""
    cursor = MagicMock()
    cursor.rowcount = rowcount
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn


def test_log_to_database_skips_empty_stream(monkeypatch):
    """#819 regression: an empty stream must skip with a warning instead of
    raising IndexError. The non-empty device in the same call must still get
    its row written and conn.commit() must be reached."""
    monkeypatch.setattr("neurobooth_terra.Table", lambda *a, **kw: MagicMock())

    conn = _mock_conn(rowcount=1)
    cursor = conn.cursor.return_value

    empty_mouse = DeviceData(
        device_id="Mouse",
        device_data={"time_stamps": np.array([])},
        marker_data=None,
        sensor_ids=["Mouse_sens_1"],
        hdf5_path="/data/session_dir/session_..._Mouse-Mouse.hdf5",
    )
    populated = DeviceData(
        device_id="Mic_Yeti",
        device_data={"time_stamps": np.array([1000.0, 1000.001, 1000.002])},
        marker_data=None,
        sensor_ids=["Mic_Yeti_sens_1"],
        hdf5_path="/data/session_dir/session_..._Mic_Yeti-Mic_Yeti.hdf5",
    )

    log_to_database([empty_mouse, populated], conn, "log_task_42")

    # Only the populated device should have triggered an UPDATE.
    assert cursor.execute.call_count == 1
    # And the transaction must have been committed (we made it past the loop).
    assert conn.commit.called


def test_log_to_database_empty_stream_first_does_not_block_subsequent(monkeypatch):
    """Order independence: an empty stream as the FIRST item in device_data
    must not prevent later items from being processed."""
    monkeypatch.setattr("neurobooth_terra.Table", lambda *a, **kw: MagicMock())

    conn = _mock_conn(rowcount=1)
    cursor = conn.cursor.return_value

    empty_first = DeviceData(
        device_id="Mouse",
        device_data={"time_stamps": np.array([])},
        marker_data=None,
        sensor_ids=["Mouse_sens_1"],
        hdf5_path="/data/session_dir/x_Mouse-Mouse.hdf5",
    )
    populated_a = DeviceData(
        device_id="Mic_Yeti",
        device_data={"time_stamps": np.array([1.0, 1.001])},
        marker_data=None,
        sensor_ids=["Mic_Yeti_sens_1"],
        hdf5_path="/data/session_dir/x_Mic_Yeti-Mic_Yeti.hdf5",
    )
    populated_b = DeviceData(
        device_id="FLIR_blackfly_1",
        device_data={"time_stamps": np.array([2.0, 2.001, 2.002])},
        marker_data=None,
        sensor_ids=["FLIR_rgb_1"],
        hdf5_path="/data/session_dir/x_FLIR-FLIR_rgb.hdf5",
    )

    log_to_database([empty_first, populated_a, populated_b], conn, "log_task_42")

    # Two populated devices, one UPDATE each (rowcount=1 short-circuit).
    assert cursor.execute.call_count == 2
    assert conn.commit.called


def test_log_to_database_all_empty_streams_still_commits(monkeypatch):
    """If every stream happens to be empty (degenerate but legal), the
    function must still reach conn.commit() rather than leaving the
    transaction open."""
    monkeypatch.setattr("neurobooth_terra.Table", lambda *a, **kw: MagicMock())

    conn = _mock_conn(rowcount=1)
    cursor = conn.cursor.return_value

    devs = [
        DeviceData(
            device_id=f"Empty_{i}",
            device_data={"time_stamps": np.array([])},
            marker_data=None,
            sensor_ids=[f"Empty_{i}_sens"],
            hdf5_path=f"/data/session_dir/x_Empty_{i}.hdf5",
        )
        for i in range(3)
    ]

    log_to_database(devs, conn, "log_task_42")

    assert cursor.execute.call_count == 0
    assert conn.commit.called
