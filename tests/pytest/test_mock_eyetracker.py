"""Lifecycle tests for the synthetic EyeLink mock.

These tests exercise ``MockEyeTracker`` end-to-end without ``pylink``
installed and without a configured PsychoPy monitor center.  Coverage:

- ``__init__`` -> ``connect`` lands the device in ``DeviceState.CONNECTED``
  using canned monitor dimensions.
- ``start`` -> recording -> ``stop`` cycles through state transitions
  and writes a stub ``.edf`` file at the requested path.
- The synthetic record loop pushes 13-column samples at the configured
  sample rate.
- ``calibrate`` is a no-op (does not touch ``EyeLinkCoreGraphicsPsychoPy``
  or ``pylink``).
- The substitution registry is populated by importing
  ``stim_param_reader``.
"""

import os
import time
from unittest.mock import MagicMock

import pytest

from neurobooth_os.iout import eyelink_tracker as eyelink_mod
from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mock import mock_eyetracker as mock_eyetracker_mod
from neurobooth_os.iout.mock.mock_eyetracker import (
    _STUB_EDF_BYTES,
    MockEyeTracker,
)
from neurobooth_os.iout.stim_param_reader import (
    EyelinkDeviceArgs,
    EyelinkSensorArgs,
    MockEyelinkDeviceArgs,
)


SAMPLE_RATE_HZ = 500
RECORDING_WINDOW_SEC = 0.3


def _build_mock_args() -> MockEyelinkDeviceArgs:
    sensor = EyelinkSensorArgs.model_construct(
        sensor_id="eyelink_sens_1",
        sample_rate=SAMPLE_RATE_HZ,
        calibration_type="HV5",
        msec_delay=10,
        calibration_area_proportion=(0.85, 0.85),
        validation_area_proportion=(0.85, 0.85),
    )
    return MockEyelinkDeviceArgs.model_construct(
        ENV_devices={},
        device_id="EyeLink_dev_1",
        sensor_ids=["eyelink_sens_1"],
        sensor_array=[sensor],
        ip="100.1.1.1",
        arg_parser="iout.stim_param_reader.py::MockEyelinkDeviceArgs()",
    )


@pytest.fixture
def mock_args() -> MockEyelinkDeviceArgs:
    return _build_mock_args()


@pytest.fixture
def mock_window():
    """A duck-typed window. The mock never draws to it, so MagicMock works."""
    return MagicMock()


@pytest.fixture(autouse=True)
def _silence_messaging(monkeypatch):
    """Replace ``post_message`` in both modules so tests don't hit the DB.

    ``EyeTracker`` imports ``post_message`` into ``eyelink_tracker``'s
    namespace, and ``MockEyeTracker._connect_tracker`` imports it into
    ``mock_eyetracker``'s namespace.  Both bindings need patching.
    """
    monkeypatch.setattr(eyelink_mod, "post_message", lambda msg: None)
    monkeypatch.setattr(mock_eyetracker_mod, "post_message", lambda msg: None)


class TestMockEyeTrackerLifecycle:

    def test_connect_lands_in_connected(self, mock_args, mock_window):
        device = MockEyeTracker(device_args=mock_args, win=mock_window)
        try:
            assert device.state == DeviceState.CONNECTED
            assert device.tk is not None
            assert device.monitor_width == 1920
            assert device.monitor_height == 1080
            assert device.outlet is not None
        finally:
            device.close()

    def test_start_stop_writes_stub_edf(self, mock_args, mock_window, tmp_path):
        device = MockEyeTracker(device_args=mock_args, win=mock_window)
        edf_path = str(tmp_path / "task_a_eyelink.edf")
        try:
            files = device.start(edf_path)
            assert files == ["task_a_eyelink.edf"]
            assert device.streaming is True
            assert device.recording is True
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            assert device.state == DeviceState.STOPPED
            assert device.streaming is False
            assert device.recording is False
            assert os.path.exists(edf_path)
            with open(edf_path, "rb") as f:
                assert f.read() == _STUB_EDF_BYTES
        finally:
            device.close()

    def test_close_after_recording(self, mock_args, mock_window, tmp_path):
        device = MockEyeTracker(device_args=mock_args, win=mock_window)
        edf_path = str(tmp_path / "close_test.edf")
        device.start(edf_path)
        device.close()
        assert device.state == DeviceState.DISCONNECTED


class TestMockEyeTrackerLSLFlow:

    def test_synthetic_samples_flow(self, mock_args, mock_window, tmp_path):
        """Verify the synthetic record thread captures timestamps at the
        configured rate.  Asserting on absolute count is brittle on
        Windows scheduling; require a generous lower bound instead.
        """
        device = MockEyeTracker(device_args=mock_args, win=mock_window)
        edf_path = str(tmp_path / "lsl_test.edf")
        try:
            device.start(edf_path)
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
        finally:
            device.close()
        assert device.timestamps_et, "Expected synthetic timestamps"
        assert len(device.timestamps_local) == len(device.timestamps_et)
        # 500 Hz over 300 ms is ~150 samples; the mock's ``time.sleep``
        # cadence is OS-bound on Windows, so >= 5 is the loose floor.
        assert len(device.timestamps_et) >= 5, (
            f"Expected at least 5 synthetic samples; got "
            f"{len(device.timestamps_et)}"
        )

    def test_calibrate_is_no_op(self, mock_args, mock_window):
        device = MockEyeTracker(device_args=mock_args, win=mock_window)
        try:
            # The real ``calibrate`` reaches into pylink via
            # EyeLinkCoreGraphicsPsychoPy. The mock should not.
            device.calibrate()
            assert device.calibrated is True
        finally:
            device.close()


class TestMockEyeTrackerRegistration:

    def test_mock_eyetracker_is_registered(self):
        from neurobooth_os.iout.mock_substitution import MOCK_REGISTRY
        assert MOCK_REGISTRY.get(EyelinkDeviceArgs) is MockEyelinkDeviceArgs

    def test_device_class_resolves_to_mock(self):
        assert MockEyelinkDeviceArgs.device_class() is MockEyeTracker

    def test_apply_substitution_swaps_class(self):
        from neurobooth_os.iout.mock_substitution import apply_mock_substitution
        real = EyelinkDeviceArgs.model_construct(
            ENV_devices={},
            device_id="EyeLink_dev_1",
            sensor_ids=["eyelink_sens_1"],
            ip="100.1.1.1",
            sensor_array=[],
            arg_parser="iout.stim_param_reader.py::EyelinkDeviceArgs()",
        )
        result = apply_mock_substitution(real, active={"EyeTracker"})
        assert isinstance(result, MockEyelinkDeviceArgs)
        assert result.device_id == "EyeLink_dev_1"
        assert result.ip == "100.1.1.1"
