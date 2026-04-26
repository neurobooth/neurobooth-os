"""Lifecycle tests for the synthetic Mbient mock.

These tests exercise ``MockMbient`` end-to-end without a real BLE device or
the mbientlab SDK installed.  They cover:

- ``bring_up`` -> ``start`` -> ``stop`` -> ``close`` round-trip with
  synthetic samples flowing.
- ``attempt_reconnect`` / ``on_task_reconnect`` / ``on_session_reset`` are
  no-ops on the mock and don't post the ``MbientDisconnected`` warning
  the real path emits.
- The substitution registry is populated by importing
  ``stim_param_reader``.
"""

import time

import pytest

from neurobooth_os.iout import mbient as mbient_mod
from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mock.mock_mbient import MockMbient
from neurobooth_os.iout.stim_param_reader import (
    MbientDeviceArgs,
    MbientSensorArgs,
    MockMbientDeviceArgs,
)


SAMPLE_RATE_HZ = 100
SAMPLE_WINDOW_SEC = 0.3


def _build_mock_args() -> MockMbientDeviceArgs:
    """Construct a ``MockMbientDeviceArgs`` with the minimum fields ``Mbient.__init__`` reads."""
    acc_sensor = MbientSensorArgs.model_construct(
        sensor_id="acc1",
        sample_rate=SAMPLE_RATE_HZ,
        data_range=8,
    )
    gyro_sensor = MbientSensorArgs.model_construct(
        sensor_id="gyro1",
        sample_rate=SAMPLE_RATE_HZ,
        data_range=2000,
    )
    return MockMbientDeviceArgs.model_construct(
        ENV_devices={},
        device_id="Mbient_TestDevice_1",
        sensor_ids=["acc1", "gyro1"],
        sensor_array=[acc_sensor, gyro_sensor],
        mac="AA:BB:CC:DD:EE:FF",
        device_name="TestDevice",
        arg_parser="iout.stim_param_reader.py::MockMbientDeviceArgs()",
    )


@pytest.fixture
def mock_args() -> MockMbientDeviceArgs:
    return _build_mock_args()


@pytest.fixture(autouse=True)
def _disable_lsl_and_messaging(monkeypatch):
    """Skip LSL outlet creation and silence ``post_message`` so tests don't need
    a real network/database. ``mbient.DISABLE_LSL`` gates outlet creation in
    ``connect()`` and the ``_lsl_data_handler`` injection in
    ``_attach_data_source``; ``post_message`` is reached via ``send_status_msg``
    in ``setup()`` regardless of that flag.
    """
    monkeypatch.setattr(mbient_mod, "DISABLE_LSL", True)
    monkeypatch.setattr(mbient_mod, "post_message", lambda msg: None)


@pytest.fixture
def captured_messages(monkeypatch):
    """Replace ``mbient.post_message`` with a recorder so tests can assert on
    what messages a code path emits.  Overrides the autouse fixture's
    silencer for the test that uses it.
    """
    posted = []
    monkeypatch.setattr(mbient_mod, "post_message", lambda msg: posted.append(msg))
    return posted


class TestMockMbientLifecycle:
    """Bring up, run, and tear down a mock Mbient end-to-end."""

    def test_bring_up_returns_self(self, mock_args):
        device = MockMbient(mock_args)
        try:
            assert device.bring_up({}) is device
            assert device.streaming is True
            assert device.state == DeviceState.STARTED
        finally:
            device.close()

    def test_synthetic_samples_flow_at_configured_rate(self, mock_args):
        device = MockMbient(mock_args)
        captured = []
        device.register_data_handler(
            lambda epoch, acc, gyro: captured.append((epoch, acc.x, gyro.x))
        )
        try:
            device.bring_up({})
            time.sleep(SAMPLE_WINDOW_SEC)
            device.stop()
        finally:
            device.close()

        # At 100 Hz over 300 ms we expect ~30 samples; allow generous slack
        # for Windows scheduling jitter and CI variance.
        assert len(captured) >= 5, (
            f"Expected at least 5 synthetic samples; got {len(captured)}"
        )
        # n_samples_streamed is incremented inside the synthetic loop and
        # should match (or exceed by 1 if a sample landed between the
        # final handler-call and our assertion).
        assert device.n_samples_streamed >= len(captured)

    def test_close_without_start_does_not_raise(self, mock_args):
        # If connect() succeeds but start() never runs (or
        # bring_up() short-circuits), close() must still tear down cleanly.
        device = MockMbient(mock_args)
        device.connect()
        device.close()
        assert device.streaming is False
        assert device._mock_thread is None

    def test_close_after_start_joins_thread(self, mock_args):
        device = MockMbient(mock_args)
        device.bring_up({})
        # Sanity-check the thread is actually running before we ask for stop.
        assert device._mock_thread is not None
        assert device._mock_thread.is_alive()
        device.close()
        assert device.streaming is False
        assert device._mock_thread is None
        assert device.state == DeviceState.DISCONNECTED

    def test_stop_then_start_again(self, mock_args):
        # Mocks should tolerate stop/start cycles within a session.
        device = MockMbient(mock_args)
        try:
            device.bring_up({})
            device.stop()
            assert device.streaming is False
            device.start()
            assert device.streaming is True
            assert device._mock_thread is not None
            assert device._mock_thread.is_alive()
        finally:
            device.close()


class TestMockMbientReconnectPaths:
    """The mock should not pretend to disconnect/reconnect or notify operators."""

    def test_attempt_reconnect_does_not_post_disconnect(
        self, mock_args, captured_messages
    ):
        device = MockMbient(mock_args)
        try:
            device.bring_up({})
            device.attempt_reconnect()  # default args mirror callback signature
            assert device.streaming is True
        finally:
            device.close()
        body_types = [
            type(m.body).__name__ for m in captured_messages if hasattr(m, "body")
        ]
        assert "MbientDisconnected" not in body_types, (
            f"MockMbient.attempt_reconnect must not post MbientDisconnected; "
            f"got {body_types}"
        )

    def test_on_task_reconnect_is_no_op(self, mock_args, captured_messages):
        device = MockMbient(mock_args)
        try:
            device.bring_up({})
            device.on_task_reconnect()
            assert device.streaming is True
        finally:
            device.close()

    def test_on_session_reset_returns_true(self, mock_args):
        device = MockMbient(mock_args)
        try:
            device.bring_up({})
            assert device.on_session_reset() is True
        finally:
            device.close()


class TestMockMbientRegistration:
    """The substitution registry is populated as a side-effect of importing
    ``stim_param_reader``; verify both the entry and the device-class hop.
    """

    def test_mock_mbient_is_registered(self):
        from neurobooth_os.iout.mock_substitution import MOCK_REGISTRY
        assert MOCK_REGISTRY.get(MbientDeviceArgs) is MockMbientDeviceArgs

    def test_device_class_resolves_to_mock(self):
        assert MockMbientDeviceArgs.device_class() is MockMbient

    def test_apply_substitution_swaps_class(self):
        # Round-trip through apply_mock_substitution to confirm the registry
        # entry resolves under the env-var-driven path that DeviceManager uses.
        from neurobooth_os.iout.mock_substitution import apply_mock_substitution
        real = MbientDeviceArgs.model_construct(
            ENV_devices={"Mbient_d_1": {"mac": "AA:BB"}},
            device_id="Mbient_d_1",
            sensor_ids=["acc1"],
            mac="AA:BB",
            device_name="d",
            arg_parser="iout.stim_param_reader.py::MbientDeviceArgs()",
            sensor_array=[],
        )
        result = apply_mock_substitution(real, active={"Mbient"})
        assert isinstance(result, MockMbientDeviceArgs)
        # Field values preserved (model_construct, not re-validation).
        assert result.device_id == "Mbient_d_1"
        assert result.mac == "AA:BB"
