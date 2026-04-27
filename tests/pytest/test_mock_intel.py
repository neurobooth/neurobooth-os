"""Lifecycle tests for the synthetic Intel RealSense mock.

Exercise ``MockVidRec_Intel`` end-to-end without ``pyrealsense2`` installed.
"""

import os
import time

import pytest

from neurobooth_os.iout import camera_intel as intel_mod
from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mock.mock_intel import (
    _STUB_BAG_BYTES,
    MockVidRec_Intel,
)
from neurobooth_os.iout.stim_param_reader import (
    IntelDeviceArgs,
    IntelSensorArgs,
    MockIntelDeviceArgs,
)


SAMPLE_RATE_HZ = 30
RECORDING_WINDOW_SEC = 0.3


def _build_mock_args() -> MockIntelDeviceArgs:
    rgb_sensor = IntelSensorArgs.model_construct(
        sensor_id="intel_rgb_sens",
        sample_rate=SAMPLE_RATE_HZ,
        width_px=640,
        height_px=480,
    )
    depth_sensor = IntelSensorArgs.model_construct(
        sensor_id="intel_depth_sens",
        sample_rate=SAMPLE_RATE_HZ,
        width_px=640,
        height_px=480,
    )
    return MockIntelDeviceArgs.model_construct(
        ENV_devices={},
        device_id="Intel_dev_1",
        sensor_ids=["intel_rgb_sens", "intel_depth_sens"],
        sensor_array=[rgb_sensor, depth_sensor],
        device_sn="MOCK_INTEL_SN",
        auto_exposure_priority=0.0,
        arg_parser="iout.stim_param_reader.py::MockIntelDeviceArgs()",
    )


@pytest.fixture
def mock_args() -> MockIntelDeviceArgs:
    return _build_mock_args()


@pytest.fixture(autouse=True)
def _silence_messaging(monkeypatch):
    """Silence ``meta.post_message`` so tests don't need a database."""
    from neurobooth_os.iout import metadator as meta_mod
    monkeypatch.setattr(meta_mod, "post_message", lambda msg: None)


class TestMockVidRecIntelLifecycle:

    def test_construct_skips_pyrealsense2(self, mock_args):
        device = MockVidRec_Intel(device_args=mock_args)
        # _configure_pipeline overridden — these stay None on the mock.
        assert device.config is None
        assert device.pipeline is None
        device.close()

    def test_connect_lands_in_connected(self, mock_args):
        device = MockVidRec_Intel(device_args=mock_args)
        try:
            device.connect()
            assert device.state == DeviceState.CONNECTED
            assert device.outlet is not None
        finally:
            device.close()

    def test_start_stop_writes_stub_bag(self, mock_args, tmp_path):
        device = MockVidRec_Intel(device_args=mock_args)
        try:
            device.connect()
            video_basename = str(tmp_path / "task_a")
            files = device.start(video_basename)
            assert files == ["task_a_intel1.bag"]
            assert device.streaming is True
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            device.ensure_stopped(timeout_seconds=2)
            bag_path = str(tmp_path / "task_a_intel1.bag")
            assert os.path.exists(bag_path)
            with open(bag_path, "rb") as fh:
                assert fh.read() == _STUB_BAG_BYTES
        finally:
            device.close()

    def test_close_after_recording(self, mock_args, tmp_path):
        device = MockVidRec_Intel(device_args=mock_args)
        device.connect()
        device.start(str(tmp_path / "close_test"))
        device.close()
        assert device.state == DeviceState.DISCONNECTED


class TestMockVidRecIntelLSLFlow:

    def test_synthetic_samples_advance_frame_counter(self, mock_args, tmp_path):
        device = MockVidRec_Intel(device_args=mock_args)
        try:
            device.connect()
            device.start(str(tmp_path / "lsl_test"))
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            device.ensure_stopped(timeout_seconds=2)
            # 30 FPS over 300ms is ~9 frames; allow generous floor for jitter.
            assert device.frame_counter >= 3
        finally:
            device.close()


class TestMockVidRecIntelRegistration:

    def test_mock_intel_is_registered(self):
        from neurobooth_os.iout.mock_substitution import MOCK_REGISTRY
        assert MOCK_REGISTRY.get(IntelDeviceArgs) is MockIntelDeviceArgs

    def test_device_class_resolves_to_mock(self):
        assert MockIntelDeviceArgs.device_class() is MockVidRec_Intel

    def test_apply_substitution_swaps_class(self):
        from neurobooth_os.iout.mock_substitution import apply_mock_substitution
        real = IntelDeviceArgs.model_construct(
            ENV_devices={},
            device_id="Intel_dev_1",
            sensor_ids=["intel_rgb_sens"],
            sensor_array=[],
            device_sn="REAL_INTEL_SN",
            auto_exposure_priority=0.0,
            arg_parser="iout.stim_param_reader.py::IntelDeviceArgs()",
        )
        # Real IntelDeviceArgs.__init__ would call rs.config() which would fail
        # without pyrealsense2; substitution should produce a MockIntelDeviceArgs
        # whose __init__ overrides mean it never touches rs.
        result = apply_mock_substitution(real, active={"VidRec_Intel"})
        assert isinstance(result, MockIntelDeviceArgs)
        assert result.device_sn == "REAL_INTEL_SN"
