"""Test ACQ's early log_sensor_file write at device-start time.

Previously (GitHub issue #659), video filenames were routed through a fragile
pipeline: ACQ -> RecordingFiles message -> CTR buffer keyed by fname ->
TaskCompletion snapshot -> backlog file -> XDF post-processing. A cancel or
crash anywhere in that chain left files on disk with no log_sensor_file row.

The fix: ACQ writes log_sensor_file rows directly after device.start(), using
the log_task_id that STM pre-created and passed in the StartRecording or
TransitionRecording message. Timing fields are left NULL; they are filled in
later by the XDF post-processing step (UPDATE-or-INSERT in log_to_database).

These tests exercise the pure registration logic by extracting what
DeviceManager._register_sensor_files would do, without importing DeviceManager
itself (whose module load has a config side effect that requires the deployed
config format).
"""

import os
from dataclasses import dataclass
from typing import List
from unittest.mock import patch, MagicMock


@dataclass
class _FakeDevice:
    device_id: str
    sensor_ids: List[str]
    video_filename: str  # Device-reported output path (used to derive session folder)


@dataclass
class _CapturedInsert:
    log_task_id: str
    device_id: str
    sensor_id: str
    sensor_file_path: str


class _CaptureTable:
    """Stand-in for neurobooth_terra.Table that records insert_rows calls."""
    def __init__(self, *args, **kwargs):
        self.inserts: List[_CapturedInsert] = []

    def insert_rows(self, vals, cols):
        for row in vals:
            # Columns: log_task_id, true_temporal_resolution,
            # true_spatial_resolution, file_start_time, file_end_time,
            # device_id, sensor_id, sensor_file_path
            log_task_id, _, _, _, _, device_id, sensor_id, sensor_file_path = row
            self.inserts.append(_CapturedInsert(
                log_task_id=log_task_id,
                device_id=device_id,
                sensor_id=sensor_id,
                sensor_file_path=sensor_file_path,
            ))


def _register(log_task_id, filename, device_files, capture, get_conn):
    """Replica of DeviceManager._register_sensor_files logic for unit testing.

    Kept in sync with neurobooth_os/iout/lsl_streamer.py. If the implementation
    changes, update this helper to match.
    """
    from neurobooth_os.iout.split_xdf import LOG_SENSOR_COLUMNS
    session_folder = os.path.basename(os.path.dirname(filename))
    try:
        conn = get_conn()
    except Exception:
        # Mirror the production behavior: database failure must not prevent
        # recording. Swallow the error.
        return False
    try:
        table = capture  # The _CaptureTable stands in for Table("log_sensor_file", conn)
        for device, basenames in device_files:
            sensor_file_paths = [f'{session_folder}/{b}' for b in basenames]
            pg_array = '{' + ', '.join(sensor_file_paths) + '}'
            for sensor_id in device.sensor_ids:
                table.insert_rows(
                    [(log_task_id, None, None, None, None,
                      device.device_id, sensor_id, pg_array)],
                    cols=LOG_SENSOR_COLUMNS,
                )
        return True
    finally:
        pass  # conn.close() would happen here in production


def test_early_write_writes_row_per_sensor():
    """Each sensor of each device gets its own log_sensor_file row."""
    device = _FakeDevice(
        device_id="Intel_D455_1",
        sensor_ids=["Intel_D455_depth_1", "Intel_D455_rgb_1"],
        video_filename="/data/subj_date/subj_date_time_task_intel1.bag",
    )
    device_files = [(device, ["subj_date_time_task_intel1.bag"])]

    capture = _CaptureTable()
    _register(
        log_task_id="log_42",
        filename="/data/subj_date/subj_date_time_task",
        device_files=device_files,
        capture=capture,
        get_conn=lambda: MagicMock(),
    )

    assert len(capture.inserts) == 2  # one per sensor
    sensor_ids = {ins.sensor_id for ins in capture.inserts}
    assert sensor_ids == {"Intel_D455_depth_1", "Intel_D455_rgb_1"}
    for ins in capture.inserts:
        assert ins.log_task_id == "log_42"
        assert ins.device_id == "Intel_D455_1"
        # Path should be session-folder-relative: "{session_folder}/{basename}"
        assert ins.sensor_file_path == "{subj_date/subj_date_time_task_intel1.bag}"


def test_iphone_multi_file_registers_all_paths():
    """iPhone produces both .mov and .json; both paths go into the same row."""
    device = _FakeDevice(
        device_id="IPhone_dev_1",
        sensor_ids=["IPhone_sens_1"],
        video_filename="/data/subj_date/subj_date_time_task_IPhone.mov",
    )
    device_files = [(device, [
        "subj_date_time_task_IPhone.mov",
        "subj_date_time_task_IPhone.json",
    ])]

    capture = _CaptureTable()
    _register(
        log_task_id="log_99",
        filename="/data/subj_date/subj_date_time_task",
        device_files=device_files,
        capture=capture,
        get_conn=lambda: MagicMock(),
    )

    assert len(capture.inserts) == 1
    path = capture.inserts[0].sensor_file_path
    assert "IPhone.mov" in path
    assert "IPhone.json" in path
    assert "subj_date/" in path  # session folder prefix


def test_db_failure_does_not_raise():
    """If get_database_connection fails, registration returns silently."""
    device = _FakeDevice(
        device_id="FLIR_blackfly_1",
        sensor_ids=["FLIR_sens_1"],
        video_filename="/data/subj_date/subj_date_time_task_flir.avi",
    )
    device_files = [(device, ["subj_date_time_task_flir.avi"])]

    def raise_on_connect():
        raise RuntimeError("database is down")

    capture = _CaptureTable()
    result = _register(
        log_task_id="log_77",
        filename="/data/subj_date/subj_date_time_task",
        device_files=device_files,
        capture=capture,
        get_conn=raise_on_connect,
    )
    # Should not raise. Insert did not happen.
    assert result is False
    assert capture.inserts == []
