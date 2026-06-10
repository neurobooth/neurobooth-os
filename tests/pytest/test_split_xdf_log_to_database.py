"""Tests for ``neurobooth_os.iout.split_xdf.log_to_database``.

Regression coverage for #819: a stream with zero samples (most commonly
Mouse, which only emits samples on movement) is legitimate data, but pre-fix
the per-device loop ran ``timestamps[0]`` unconditionally and raised
IndexError on the empty case. The exception propagated out of
``log_to_database`` before ``conn.commit()`` was reached, rolling back every
device's pending UPDATE/INSERT and leaving the entire task's
``log_sensor_file`` rows empty.

The empty-stream device's HDF5 file is still written by ``write_device_hdf5``,
so ``log_to_database`` must still register it -- with NULL timing -- otherwise
the file is orphaned on disk and the copy script reports
``log_sensor_file_id not found`` for it on every run.
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


def test_log_to_database_registers_empty_stream_with_null_timing(monkeypatch):
    """#819: an empty stream must NOT raise IndexError, and its HDF5 file must
    still be registered -- with NULL timing fields -- so it is not orphaned.
    The non-empty device in the same call must also register, with real
    timing, and conn.commit() must be reached."""
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

    # Both devices register: one UPDATE each (rowcount=1 short-circuits).
    assert cursor.execute.call_count == 2

    # The empty Mouse (processed first) registers with NULL timing but a real
    # HDF5 path. UPDATE bound params are
    # (temporal_resolution, file_start_time, file_end_time, hdf5_rel, ...).
    empty_params = cursor.execute.call_args_list[0][0][1]
    assert empty_params[0] is None  # true_temporal_resolution
    assert empty_params[1] is None  # file_start_time
    assert empty_params[2] is None  # file_end_time
    assert empty_params[3] is not None  # the HDF5 path IS registered

    # The populated device registers with real (non-NULL) timing.
    pop_params = cursor.execute.call_args_list[1][0][1]
    assert pop_params[0] is not None
    assert pop_params[1] is not None
    assert pop_params[2] is not None

    assert conn.commit.called


def test_log_to_database_empty_stream_first_does_not_block_subsequent(monkeypatch):
    """Order independence: an empty stream as the FIRST item in device_data
    must register itself AND not prevent later items from being processed."""
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

    # All three devices register, one UPDATE each (rowcount=1 short-circuit).
    assert cursor.execute.call_count == 3
    assert conn.commit.called


def test_log_to_database_all_empty_streams_register_and_commit(monkeypatch):
    """If every stream happens to be empty (degenerate but legal), each file is
    still registered (with NULL timing) and the function reaches conn.commit()
    rather than leaving the transaction open."""
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

    # Each empty device registers its file with NULL timing.
    assert cursor.execute.call_count == 3
    for call in cursor.execute.call_args_list:
        params = call[0][1]
        assert params[0] is None  # true_temporal_resolution
        assert params[1] is None  # file_start_time
        assert params[2] is None  # file_end_time
        assert params[3] is not None  # HDF5 path registered
    assert conn.commit.called
