"""Lifecycle tests for the synthetic microphone mock.

Exercise ``MockMicStream`` end-to-end without ``pyaudio`` installed.
"""

import time

import pytest

from neurobooth_os.iout import microphone as mic_mod
from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mock.mock_microphone import MockMicStream
from neurobooth_os.iout.stim_param_reader import (
    MicYetiDeviceArgs,
    MicYetiSensorArgs,
    MockMicYetiDeviceArgs,
)


SAMPLE_RATE_HZ = 22050
CHUNK_SIZE = 1024
RECORDING_WINDOW_SEC = 0.3


def _build_mock_args() -> MockMicYetiDeviceArgs:
    sensor = MicYetiSensorArgs.model_construct(
        sensor_id="mic_sens_1",
        sample_rate=SAMPLE_RATE_HZ,
        sample_chunk_size=CHUNK_SIZE,
        input=True,
        output=False,
        channels=1,
        format="paInt16",
    )
    return MockMicYetiDeviceArgs.model_construct(
        ENV_devices={},
        device_id="Mic_Yeti_dev_1",
        sensor_ids=["mic_sens_1"],
        sensor_array=[sensor],
        microphone_name="MockYeti",
        device_name="MockYeti",
        arg_parser="iout.stim_param_reader.py::MockMicYetiDeviceArgs()",
    )


@pytest.fixture
def mock_args() -> MockMicYetiDeviceArgs:
    return _build_mock_args()


@pytest.fixture(autouse=True)
def _silence_messaging(monkeypatch):
    """Silence ``post_message`` so tests don't need a database."""
    monkeypatch.setattr(mic_mod, "post_message", lambda msg: None)


class TestMockMicStreamLifecycle:

    def test_connect_lands_in_connected(self, mock_args):
        device = MockMicStream(device_args=mock_args)
        try:
            device.connect()
            assert device.state == DeviceState.CONNECTED
            assert device.outlet_audio is not None
            assert device.device_name.startswith("MockMicrophone-")
        finally:
            device.close()

    def test_start_stop_cycle(self, mock_args):
        device = MockMicStream(device_args=mock_args)
        try:
            device.connect()
            device.start()
            assert device.streaming is True
            assert device.state == DeviceState.STARTED
            time.sleep(RECORDING_WINDOW_SEC)
            device.stop()
            assert device.streaming is False
            assert device.state == DeviceState.STOPPED
        finally:
            device.close()

    def test_close_after_recording(self, mock_args):
        device = MockMicStream(device_args=mock_args)
        device.connect()
        device.start()
        device.close()
        assert device.streaming is False
        assert device.state in (DeviceState.STOPPED, DeviceState.DISCONNECTED)


class TestMockMicStreamRegistration:

    def test_mock_microphone_is_registered(self):
        from neurobooth_os.iout.mock_substitution import MOCK_REGISTRY
        assert MOCK_REGISTRY.get(MicYetiDeviceArgs) is MockMicYetiDeviceArgs

    def test_device_class_resolves_to_mock(self):
        assert MockMicYetiDeviceArgs.device_class() is MockMicStream

    def test_apply_substitution_swaps_class(self):
        from neurobooth_os.iout.mock_substitution import apply_mock_substitution
        sensor = MicYetiSensorArgs.model_construct(
            sensor_id="mic_sens_1",
            sample_rate=SAMPLE_RATE_HZ,
            sample_chunk_size=CHUNK_SIZE,
            input=True,
            output=False,
            channels=1,
            format="paInt16",
        )
        real = MicYetiDeviceArgs.model_construct(
            ENV_devices={},
            device_id="Mic_Yeti_dev_1",
            sensor_ids=["mic_sens_1"],
            sensor_array=[sensor],
            microphone_name="Yeti",
            arg_parser="iout.stim_param_reader.py::MicYetiDeviceArgs()",
        )
        result = apply_mock_substitution(real, active={"MicStream"})
        assert isinstance(result, MockMicYetiDeviceArgs)
        assert result.microphone_name == "Yeti"
        # Nested sensor models must survive the swap as model instances —
        # MicStream.__init__ reaches them via attribute access, and a regression
        # to ``model_dump()`` would replace them with plain dicts here.
        assert isinstance(result.sensor_array[0], MicYetiSensorArgs)
        assert result.sensor_array[0].sample_chunk_size == CHUNK_SIZE
