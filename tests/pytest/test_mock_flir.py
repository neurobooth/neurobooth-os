"""Lifecycle tests for the synthetic FLIR mock.

Exercise ``MockVidRec_Flir`` end-to-end without ``PySpin`` installed.
"""

import os
import time

import pytest

from neurobooth_os.iout import flir_cam as flir_mod
from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mock.mock_flir import MockVidRec_Flir
from neurobooth_os.iout.stim_param_reader import (
    FlirDeviceArgs,
    FlirSensorArgs,
    MockFlirDeviceArgs,
)


SAMPLE_RATE_HZ = 60
RECORDING_WINDOW_SEC = 0.3


def _build_mock_args() -> MockFlirDeviceArgs:
    sensor = FlirSensorArgs.model_construct(
        sensor_id="flir_sens_1",
        sample_rate=SAMPLE_RATE_HZ,
        width_px=1024,
        height_px=768,
        offsetX=0,
        offsetY=0,
        exposure=4000,
        gain=10,
        gamma=1.0,
        fd=1,
    )
    return MockFlirDeviceArgs.model_construct(
        ENV_devices={},
        device_id="FLIR_dev_1",
        sensor_ids=["flir_sens_1"],
        sensor_array=[sensor],
        device_sn="MOCK_SN_1234",
        arg_parser="iout.stim_param_reader.py::MockFlirDeviceArgs()",
    )


@pytest.fixture
def mock_args() -> MockFlirDeviceArgs:
    return _build_mock_args()


@pytest.fixture(autouse=True)
def _silence_messaging(monkeypatch):
    """Silence ``post_message`` so tests don't need a database.

    FLIR uses ``meta.post_message`` (the meta module) not a local import,
    so we patch the module-level reference there.
    """
    from neurobooth_os.iout import metadator as meta_mod
    monkeypatch.setattr(meta_mod, "post_message", lambda msg: None)


class TestMockVidRecFlirLifecycle:

    def test_connect_lands_in_connected(self, mock_args):
        device = MockVidRec_Flir(device_args=mock_args)
        try:
            device.connect()
            assert device.state == DeviceState.CONNECTED
            assert device.outlet is not None
            assert device.cam is not None
            assert device.open is True
        finally:
            device.close()

    def test_start_stop_writes_video(self, mock_args, tmp_path):
        device = MockVidRec_Flir(device_args=mock_args)
        try:
            device.connect()
            video_basename = str(tmp_path / "task_a")
            files = device.start(video_basename)
            assert files == ["task_a_flir.avi"]
            assert device.streaming is True
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            device.ensure_stopped(timeout_seconds=2)
            video_path = str(tmp_path / "task_a_flir.avi")
            assert os.path.exists(video_path)
            assert os.path.getsize(video_path) > 0
        finally:
            device.close()

    def test_frame_preview_returns_png_bytes(self, mock_args):
        device = MockVidRec_Flir(device_args=mock_args)
        try:
            device.connect()
            preview = device.frame_preview()
            assert isinstance(preview, bytes)
            assert len(preview) > 0
            # cv2.imencode produces a real PNG; check the magic bytes.
            assert preview[:8] == b"\x89PNG\r\n\x1a\n"
        finally:
            device.close()


class TestMockVidRecFlirRegistration:

    def test_mock_flir_is_registered(self):
        from neurobooth_os.iout.mock_substitution import MOCK_REGISTRY
        assert MOCK_REGISTRY.get(FlirDeviceArgs) is MockFlirDeviceArgs

    def test_device_class_resolves_to_mock(self):
        assert MockFlirDeviceArgs.device_class() is MockVidRec_Flir

    def test_apply_substitution_swaps_class(self):
        from neurobooth_os.iout.mock_substitution import apply_mock_substitution
        real = FlirDeviceArgs.model_construct(
            ENV_devices={},
            device_id="FLIR_dev_1",
            sensor_ids=["flir_sens_1"],
            device_sn="REAL_SN",
            sensor_array=[],
            arg_parser="iout.stim_param_reader.py::FlirDeviceArgs()",
        )
        result = apply_mock_substitution(real, active={"VidRec_Flir"})
        assert isinstance(result, MockFlirDeviceArgs)
        assert result.device_sn == "REAL_SN"
