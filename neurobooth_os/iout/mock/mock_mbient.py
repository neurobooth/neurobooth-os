"""Synthetic Mbient that emits LSL samples without real hardware.

Overrides the two hardware hooks on :class:`Mbient`
(``_acquire_hardware`` and ``_attach_data_source``) plus the lifecycle
methods that touch the native MetaWear/warble libraries
(``start`` / ``stop`` / ``disconnect`` / ``close`` / ``reset`` /
``attempt_reconnect`` / ``on_task_reconnect`` / ``reset_and_reconnect``).

Synthetic samples are produced by a daemon thread that calls every
registered data handler at the higher of the configured ``acc_hz`` /
``gyro_hz`` rates.  The values are constants (1g down, zero rotation);
downstream code only needs the LSL samples to flow at the right
shape and rate, not to look like real motion.
"""

from __future__ import annotations

import threading
import time
from typing import Any, List, Optional

from neurobooth_os.iout.device import DeviceState
from neurobooth_os.iout.mbient import BatteryState, Mbient


class _MockSample:
    """Minimal stand-in for the mbientlab acc/gyro vector.

    Only ``.x`` / ``.y`` / ``.z`` are accessed by ``Mbient._lsl_data_handler``,
    so that's all we need.
    """

    __slots__ = ("x", "y", "z")

    def __init__(self, x: float, y: float, z: float) -> None:
        self.x = x
        self.y = y
        self.z = z


class _MockMetaWearWrapper:
    """Stub satisfying the ``device_wrapper`` calls inherited from ``Mbient``.

    Inherited code paths in ``Mbient.start`` / ``stop`` / ``disconnect``
    / ``log_battery_info`` reach into ``device_wrapper``; without this
    stub they would raise ``AttributeError`` on the mock.  Every method
    is a no-op; ``is_connected`` reflects the most recent ``disconnect``
    call so tests that inspect it see the expected transition.
    """

    def __init__(self, dev_name: str) -> None:
        self.dev_name = dev_name
        self.model_name = "MockMetaMotion"
        self.is_connected = True
        self.on_disconnect = lambda status: None

    def setup_connection_settings(self, *_args, **_kwargs) -> None:
        return None

    def setup_sensor_settings(self, *_args, **_kwargs) -> None:
        # Real return is a SensorSignals tuple consumed by the fuser; the
        # mock skips that path in ``_attach_data_source`` so None is fine.
        return None

    def enable_inertial_sampling(self) -> None:
        return None

    def disable_inertial_sampling(self) -> None:
        return None

    def start_inertial_sampling(self) -> None:
        return None

    def stop_inertial_sampling(self) -> None:
        return None

    def disconnect(self) -> None:
        self.is_connected = False
        self.on_disconnect(0)

    def reset_device(self) -> None:
        return None

    def get_battery_state(self) -> BatteryState:
        return BatteryState(voltage=4000.0, charge=100.0)


class MockMbient(Mbient):
    """Mock Mbient that emits synthetic LSL samples on a daemon thread."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._mock_thread: Optional[threading.Thread] = None
        self._mock_stop_event = threading.Event()

    def _acquire_hardware(self) -> None:
        # Skip BLE scan / connect / reset.  Install a stub wrapper so the
        # inherited start/stop/disconnect paths have something to call.
        self.device_wrapper = _MockMetaWearWrapper(self.dev_name)
        self.logger.info(self.format_message(
            "MockMbient: skipped BLE acquire (no hardware)"))

    def _attach_data_source(self) -> None:
        # Match the real path's effect on ``data_handlers`` so LSL is
        # called first, but skip the fuser/cbindings entirely.
        from neurobooth_os.iout.mbient import DISABLE_LSL  # noqa: WPS433
        if DISABLE_LSL:
            self.logger.warning("LSL Disabled!")
        else:
            self.data_handlers = [self._lsl_data_handler, *self.data_handlers]
        self.logger.info(self.format_message(
            "MockMbient: synthetic data source attached"))

    def start(self, filename: Optional[str] = None, buzz: bool = False) -> List[str]:
        """Begin emitting synthetic samples on a background thread."""
        self.streaming = True
        self.state = DeviceState.STARTED
        self._mock_stop_event.clear()
        # Use the higher of the two rates: the real fuser emits one sample
        # per matched (acc, gyro) pair which arrive at the higher rate.
        rate_hz = max(self.acc_hz, self.gyro_hz)
        self._mock_thread = threading.Thread(
            target=self._synthetic_loop,
            args=(rate_hz,),
            daemon=True,
            name=f"MockMbient-{self.dev_name}",
        )
        self._mock_thread.start()
        return []

    def stop(self) -> None:
        """Halt the synthetic-sample thread."""
        self._mock_stop_event.set()
        if self._mock_thread is not None:
            self._mock_thread.join(timeout=1.0)
            self._mock_thread = None
        self.streaming = False
        self.state = DeviceState.STOPPED

    def disconnect(self) -> None:
        if self.device_wrapper is not None:
            self.device_wrapper.disconnect()
        self.state = DeviceState.DISCONNECTED

    def close(self) -> None:
        if self.streaming:
            self.stop()
        self.subscribed_signals.clear()
        self.state = DeviceState.STOPPED
        self.disconnect()

    def reset(self, timeout_sec: float = 10) -> None:
        # Real reset waits on a native disconnect callback; the mock
        # bypasses both the reset and the wait.
        return None

    def attempt_reconnect(
        self,
        status: Optional[int] = None,
        notify: bool = True,
        n_attempts: int = 3,
    ) -> None:
        # No native BLE link to recover; surface a benign log so tests
        # can assert the path was exercised without sending the
        # MbientDisconnected message that real disconnect would.
        self.logger.info(self.format_message(
            "MockMbient: attempt_reconnect (no-op)"))

    def on_task_reconnect(self) -> None:
        # Bypass ``Mbient.task_start_reconnect``, which performs a BLE
        # scan and gates retries on real hardware availability.
        return None

    def reset_and_reconnect(self, timeout_sec: float = 10) -> bool:
        # Operator action; nothing to reset, always succeed.
        self.logger.info(self.format_message(
            "MockMbient: reset_and_reconnect (no-op)"))
        return True

    def _synthetic_loop(self, rate_hz: int) -> None:
        """Emit acc+gyro samples until ``_mock_stop_event`` is set."""
        period = 1.0 / float(rate_hz)
        # Constant values: 1g down at rest, zero rotation.  Downstream
        # consumers only need the LSL stream shape and cadence, not
        # realistic motion.
        acc = _MockSample(0.0, 0.0, 1.0)
        gyro = _MockSample(0.0, 0.0, 0.0)
        while not self._mock_stop_event.is_set():
            self.n_samples_streamed += 1
            epoch_ms = time.time() * 1000.0
            for handler in list(self.data_handlers):
                try:
                    handler(epoch_ms, acc, gyro)
                except Exception:  # pragma: no cover — defensive
                    self.logger.exception(self.format_message(
                        "MockMbient: data handler raised"))
            self._mock_stop_event.wait(period)
