import sys
import argparse
import uuid
from ctypes import c_void_p
from time import sleep, time
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, wait
import logging
from typing import Any, Dict, List, Callable, NamedTuple, Optional
from abc import ABC, abstractmethod
from enum import IntEnum

from mbientlab.warble import BleScanner
from mbientlab.metawear import MetaWear, libmetawear, parse_value, cbindings, Module, Model

from neurobooth_os.iout.stim_param_reader import MbientDeviceArgs
from neurobooth_os.log_manager import APP_LOG_NAME

# --------------------------------------------------------------------------------
# Module-level constants and debugging flags
# --------------------------------------------------------------------------------
DISABLE_LSL: bool = False  # If True, LSL streams will not be created nor will received data be pushed.
if not DISABLE_LSL:  # Conditional imports based on flags
    from pylsl import StreamInfo, StreamOutlet
    from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


# --------------------------------------------------------------------------------
# Exception Classes
# --------------------------------------------------------------------------------
class MbientError(Exception):
    pass


class UnsupportedDevice(MbientError):
    pass


class MbientFailedConnection(MbientError):
    pass


class MbientResetTimeout(MbientError):
    pass


# --------------------------------------------------------------------------------
# Mbientlab Wrapper and Procedures
#
# Provides an additional layer of abstraction around mbientlab functions.
# Can be used by external scripts (e.g., reset device script).
# --------------------------------------------------------------------------------
def scan_BLE(timeout_sec: float = 10, n_devices: int = 5) -> Dict[str, str]:
    """
    Scan to identify the MAC Address for Mbient devices. See https://mbientlab.com/tutorials/PyLinux.html#usage

    :param timeout_sec: How long to scan before giving up.
    :param n_devices: The number of expected devices. Stop scanning once this count is reached.
    :returns: A dictionary of device names as keys and MAC addresses as values.
    """
    devices = {}
    event = mp.Event()
    lock = mp.Lock()

    def handler(result):
        """Callback function invoked when a new device is identified."""
        if not result.has_service_uuid(MetaWear.GATT_SERVICE):
            return  # We only care about Mbient devices

        with lock:  # Update the result dictionary and signal completion if we found enough devices
            devices[result.name] = result.mac
            if len(devices) >= n_devices:
                event.set()

    BleScanner.set_handler(handler)
    BleScanner.start()
    event.wait(timeout=timeout_sec)
    BleScanner.stop()
    return devices


def connect_device(
        mac_address: str,
        n_attempts: int,
        retry_delay_sec: float = 1,
        log_fn: Callable[[str], None] = lambda msg: None,
) -> MetaWear:
    """
    Attempt to connect to a device with the given MAC address.

    :param mac_address: The address of the device to connect to.
    :param n_attempts: The number of connection attempts.
    :param retry_delay_sec: How long to wait after a failed attempt before retrying.
    :param log_fn: Function used to log messages.
    :returns: The MetaWear object for interfacing with the BLE device.
    """
    device = MetaWear(mac_address)

    success = False
    log_fn(f'Attempting connection to {mac_address}')
    for attempt in range(n_attempts):
        try:
            if attempt > 0:  # Do not immediately try to reconnect if it just failed.
                sleep(retry_delay_sec)

            device.connect()
            success = True
            break
        except Exception as e:
            log_fn(f'Failed to connect to {mac_address} on attempt {attempt + 1}: {e}')

    if not success:
        raise MbientFailedConnection(f'Unable to connect to {mac_address}!')

    log_fn(f'Connected to {mac_address} via {"USB" if device.usb.is_connected else "BLE"}')
    return device


# This procedure is external to the wrapper so that it can be called on an unwrapped device object in the reset script
def reset_device(device: MetaWear) -> None:
    """
    Reset the device. See https://mbientlab.com/tutorials/PyLinux.html#reset
    :param device: The connected device object to reset
    """
    board = device.board
    libmetawear.mbl_mw_logging_stop(board)
    libmetawear.mbl_mw_logging_flush_page(board)
    libmetawear.mbl_mw_logging_clear_entries(board)
    libmetawear.mbl_mw_event_remove_all(board)
    libmetawear.mbl_mw_macro_erase_all(board)
    libmetawear.mbl_mw_debug_reset_after_gc(board)
    libmetawear.mbl_mw_debug_disconnect(board)


class CallbackManager:
    """
    Helper class to provide limited scope and blocking function for mbientlab callbacks.
    Example of code that can be refactored to use this helper:
    https://github.com/mbientlab/MetaWear-SDK-Python/blob/master/examples/data_processor.py
    """

    def __init__(self, binding: cbindings.CFUNCTYPE):
        """
        :param binding: FnVoid_VoidP_DataP or FnVoid_VoidP_VoidP, depending on the what the callback is subscribed to.
        """
        self.callback_completed_event = mp.Event()
        self.callback_value = None
        self.callback = binding(self._callback)

    def _callback(self, context: Any, value: Any) -> None:
        self.callback_value = value
        self.callback_completed_event.set()

    def wait_on_value(self) -> Any:
        self.callback_completed_event.wait()
        return self.callback_value


class ConnectionParameters(NamedTuple):
    """
    Arguments for mbl_mw_settings_set_connection_parameters
    See: https://mbientlab.com/documents/metawear/cpp/latest/settings_8h.html#a1cf3cae052fe7981c26124340a41d66d
    """
    min_conn_interval: float = 7.5
    max_conn_interval: float = 7.5
    latency: int = 0
    timeout: int = 6000


class SensorParameters(NamedTuple):
    """
    Generic parameters for a sensor.
    See: https://mbientlab.com/documents/metawear/cpp/latest/accelerometer_8h.html#a5b7609e6a950d87215be8bea52ffe48c
    See: https://mbientlab.com/documents/metawear/cpp/latest/gyro__bosch_8h.html#ab6c0e565c919ee7ccb859d03e06b29d5
    """
    sample_rate: float  # Hz; anything beyond 100 may not work well
    data_range: float  # gs for accelerometer, degrees per second for gyroscope


class BatteryState(NamedTuple):
    """See https://mbientlab.com/documents/metawear/cpp/latest/structMblMwBatteryState.html"""
    voltage: float  # mV
    charge: float  # Percent, [0-100]


class SensorSignals(NamedTuple):
    """The data signal objects for each onboard sensor."""
    accel_signal: Any
    gyro_signal: Any


class GyroscopeType(IntEnum):
    """
    Gyroscope type constants (can't seem to find the in the mbientlab library...)

    See: https://mbientlab.com/documents/metawear/cpp/latest/gyro__bosch_8h.html
    MBL_MW_MODULE_GYRO_TYPE_BMI160 = 0
    MBL_MW_MODULE_GYRO_TYPE_BMI270 = 1
    """
    BMI160 = 0
    BMI270 = 1


class MetaWearWrapper(ABC):
    """
    A wrapper around a MetaWear object that provices an additional layer of abstraction.
    """
    SUPPORTED_DEVICE_MODELS = [  # Should be the models with both accelerometer and gyroscope
        Model.METAMOTION_S,
        Model.METAMOTION_R,
        Model.METAMOTION_RL,
        Model.METAMOTION_C,
        Model.METAWEAR_RG,
        Model.METAWEAR_RPRO
    ]

    @staticmethod
    def create_wrapper(device: MetaWear) -> 'MetaWearWrapper':
        """
        Inspect the device and return an appropriate wrapper subclass.

        :param device: The MetaWear object to wrap.
        :returns: An appropriate wrapper selected based on the board's configuration.
        """
        board = device.board
        model = libmetawear.mbl_mw_metawearboard_get_model(board)
        if model not in MetaWearWrapper.SUPPORTED_DEVICE_MODELS:
            model_name = libmetawear.mbl_mw_metawearboard_get_model_name(board).decode()
            raise UnsupportedDevice(f'Unsupported Device Model: {model_name}')

        gyro_type = libmetawear.mbl_mw_metawearboard_lookup_module(board, Module.GYRO)
        if gyro_type == GyroscopeType.BMI270:
            return MetaWearWrapperBMI270(device)
        elif gyro_type == GyroscopeType.BMI160:
            return MetaWearWrapperBMI160(device)
        else:
            raise UnsupportedDevice(f'Unrecognized gyroscope return value: {gyro_type}')

    def __init__(self, device):
        self.device = device
        self.board = device.board
        self.disconnect = self.device.disconnect  # Convenience binding
        self.model_name = libmetawear.mbl_mw_metawearboard_get_model_name(self.board).decode()
        self.battery_state: Optional[BatteryState] = None

    # The on_disconnect property of the wrapper binds to the wrapped MetaWear object for convenience
    @property
    def on_disconnect(self) -> Callable:
        return self.device.on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, callback_fn: Callable[[int], None]):
        self.device.on_disconnect = callback_fn

    @property
    def is_connected(self) -> bool:
        return self.device.is_connected

    def setup_connection_settings(self, connection_params: ConnectionParameters) -> None:
        """
        Configure the connection settings and transmission power.
        See: https://mbientlab.com/documents/metawear/cpp/latest/settings_8h.html#a1cf3cae052fe7981c26124340a41d66d
        See: https://mbientlab.com/documents/metawear/cpp/latest/settings_8h.html#a335f712d5fc0587eff9671b8b105d3ed

        :param connection_params: Arguments for mbl_mw_settings_set_connection_parameters.
        """
        libmetawear.mbl_mw_settings_set_connection_parameters(
            self.board,
            connection_params.min_conn_interval,
            connection_params.max_conn_interval,
            connection_params.latency,
            connection_params.timeout,
        )
        libmetawear.mbl_mw_settings_set_tx_power(self.board, 8)
        sleep(1)

    @abstractmethod
    def setup_sensor_settings(self, accel_params: SensorParameters, gyro_params: SensorParameters) -> SensorSignals:
        """
        Configure the settings of the accelerometer and gyroscope.
        See: https://mbientlab.com/documents/metawear/cpp/latest/accelerometer_8h.html
        See: https://mbientlab.com/documents/metawear/cpp/latest/gyro__bosch_8h.html

        :param accel_params: Settings for the accelerometer.
        :param gyro_params: Settings for the gyroscope.
        :returns: A NamedTuple containing the signal objects for the accelerometer and gyroscope.
        """
        raise NotImplementedError()

    @staticmethod
    def create_data_fusion_processor(sensor_signals: SensorSignals) -> Any:
        """
        Create a data processor that fuses the accelerometer and gyroscope signals.
        See: https://github.com/mbientlab/MetaWear-SDK-Python/blob/master/examples/data_processor.py

        :param sensor_signals: A NamedTuple containing the signal objects for the accelerometer and gyroscope.
        :returns: The data processor object that scan be subscribed to.
        """
        callback_manager = CallbackManager(binding=cbindings.FnVoid_VoidP_VoidP)
        signals = (c_void_p * 1)()  # This is sorcery, but it's how the examples do things...
        signals[0] = sensor_signals.gyro_signal
        libmetawear.mbl_mw_dataprocessor_fuser_create(
            sensor_signals.accel_signal, signals, 1, None, callback_manager.callback
        )
        return callback_manager.wait_on_value()

    def get_battery_state(self) -> BatteryState:
        """
        :returns: The device's battery voltage and charge.
        """
        callback_manager = CallbackManager(binding=cbindings.FnVoid_VoidP_DataP)
        signal = libmetawear.mbl_mw_settings_get_battery_state_data_signal(self.board)
        libmetawear.mbl_mw_datasignal_subscribe(signal, None, callback_manager.callback)
        libmetawear.mbl_mw_datasignal_read(signal)
        battery_state = parse_value(callback_manager.wait_on_value(), n_elem=1)
        libmetawear.mbl_mw_datasignal_unsubscribe(signal)
        return BatteryState(voltage=battery_state.voltage, charge=battery_state.charge)

    def buzz(self, motor_strength: float, buzz_time_sec: float) -> None:
        """
        Buzz the sensor for the specified amount of time and wait.

        :param motor_strength: Motor strength as a percent (0-100)
        :param buzz_time_sec: Buzz time in seconds
        """
        if motor_strength < 0 or motor_strength > 100:
            raise ValueError(f'Invalid motor strength: {motor_strength}')
        buzz_time_ms = int(buzz_time_sec * 1e3)
        libmetawear.mbl_mw_haptic_start_motor(self.board, motor_strength, buzz_time_ms)
        sleep(buzz_time_sec)

    @abstractmethod
    def enable_inertial_sampling(self) -> None:
        """
        Enable sampling on the accelerometer and gyroscope.
        """
        raise NotImplementedError()

    @abstractmethod
    def disable_inertial_sampling(self) -> None:
        """
        Disable sampling on the accelerometer and gyroscope.
        """
        raise NotImplementedError()

    @abstractmethod
    def start_inertial_sampling(self) -> None:
        """
        Start sampling on the accelerometer and gyroscope.
        """
        raise NotImplementedError()

    @abstractmethod
    def stop_inertial_sampling(self) -> None:
        """
        Stop sampling on the accelerometer and gyroscope.
        """
        raise NotImplementedError()

    def reset_device(self) -> None:
        """
        Reset the device. See https://mbientlab.com/tutorials/PyLinux.html#reset
        """
        reset_device(self.device)


class MetaWearWrapperBMI270(MetaWearWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setup_sensor_settings(self, accel_params: SensorParameters, gyro_params: SensorParameters) -> SensorSignals:
        # Configure accelerometer
        libmetawear.mbl_mw_acc_set_odr(self.board, accel_params.sample_rate)
        libmetawear.mbl_mw_acc_set_range(self.board, accel_params.data_range)
        libmetawear.mbl_mw_acc_write_acceleration_config(self.board)

        # Configure gyroscope
        libmetawear.mbl_mw_gyro_bmi270_set_odr(self.board, gyro_params.sample_rate)
        libmetawear.mbl_mw_gyro_bmi270_set_range(self.board, gyro_params.data_range)
        libmetawear.mbl_mw_gyro_bmi270_write_config(self.board)

        # Get data signals
        acc = libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.board)
        gyro = libmetawear.mbl_mw_gyro_bmi270_get_rotation_data_signal(self.board)
        return SensorSignals(accel_signal=acc, gyro_signal=gyro)

    def enable_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.board)
        libmetawear.mbl_mw_gyro_bmi270_enable_rotation_sampling(self.board)

    def disable_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_disable_acceleration_sampling(self.board)
        libmetawear.mbl_mw_gyro_bmi270_disable_rotation_sampling(self.board)

    def start_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_start(self.board)
        libmetawear.mbl_mw_gyro_bmi270_start(self.board)

    def stop_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_stop(self.board)
        libmetawear.mbl_mw_gyro_bmi270_stop(self.board)


class MetaWearWrapperBMI160(MetaWearWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setup_sensor_settings(self, accel_params: SensorParameters, gyro_params: SensorParameters) -> SensorSignals:
        # Configure accelerometer
        libmetawear.mbl_mw_acc_set_odr(self.board, accel_params.sample_rate)
        libmetawear.mbl_mw_acc_set_range(self.board, accel_params.data_range)
        libmetawear.mbl_mw_acc_write_acceleration_config(self.board)

        # Configure gyroscope
        libmetawear.mbl_mw_gyro_bmi160_set_odr(self.board, gyro_params.sample_rate)
        libmetawear.mbl_mw_gyro_bmi160_set_range(self.board, gyro_params.data_range)
        libmetawear.mbl_mw_gyro_bmi160_write_config(self.board)

        # Get data signals
        acc = libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.board)
        gyro = libmetawear.mbl_mw_gyro_bmi160_get_rotation_data_signal(self.board)
        return SensorSignals(accel_signal=acc, gyro_signal=gyro)

    def enable_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.board)
        libmetawear.mbl_mw_gyro_bmi160_enable_rotation_sampling(self.board)

    def disable_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_disable_acceleration_sampling(self.board)
        libmetawear.mbl_mw_gyro_bmi160_disable_rotation_sampling(self.board)

    def start_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_start(self.board)
        libmetawear.mbl_mw_gyro_bmi160_start(self.board)

    def stop_inertial_sampling(self) -> None:
        libmetawear.mbl_mw_acc_stop(self.board)
        libmetawear.mbl_mw_gyro_bmi160_stop(self.board)


# --------------------------------------------------------------------------------
# Object-Oriented Interface for Neurobooth-OS
# --------------------------------------------------------------------------------
class Mbient:
    """
    Handles interactions with an Mbient wearable sensor.
    Intended Lifecycle:
        1. Create object.
        2. prepare() to connect to and configure the sensor.
        3. start() to begin data collection.
        4. stop() to cease data collection. Note: Recalling start() after this may not work. Needs testing.
        5. close() to disconnect the sensor.
    If the sensor disconnects at any point, a reconnect will be attempted.
    """
    # Class variables to ensure that the BLE scan only happens during one prepare() call.
    # Will need to switch to a multiprocess.Manager if intending to use multiprocessing.
    SCAN_LOCK = mp.Lock()
    SCAN_PERFORMED = False

    # Type definitions
    DATA_HANDLER = Callable[[float, Any, Any], None]

    def __init__(
        self,
        device_args: MbientDeviceArgs,
        buzz_time_sec: float = 0,
        try_nmax: int = 5,
    ):
        self.mac = device_args.mac
        self.dev_name = device_args.device_name
        self.device_id = device_args.device_id
        self.sensor_ids = device_args.sensor_ids
        self.outlet_id = str(uuid.uuid4())
        self.buzz_time = buzz_time_sec
        self.max_connect_attempts = try_nmax
        self.retry_delay_sec = 1

        # Device configuration settings
        for sensor in device_args.sensor_array:
            if "acc" in sensor.sensor_id:
                self.acc_hz = int(sensor.sample_rate)
            elif "gyro" in sensor.sensor_id:
                self.gyro_hz = int(sensor.sample_rate)

        self.connection_params = ConnectionParameters()  # Use the default params
        self.accel_params = SensorParameters(sample_rate=self.acc_hz, data_range=16.0)
        self.gyro_params = SensorParameters(sample_rate=self.gyro_hz, data_range=2000)

        # Uninitialized Variables
        self.device_wrapper: Optional[MetaWearWrapper] = None
        self.subscribed_signals: List[Any] = []
        self.outlet: Optional[StreamOutlet] = None
        self.data_handlers: List['Mbient.DATA_HANDLER'] = []

        # Streaming-related variables
        self.callback = cbindings.FnVoid_VoidP_DataP(self._callback)
        self.streaming: bool = False
        self.n_samples_streamed = 0

        self.logger = logging.getLogger(APP_LOG_NAME)
        self.logger.debug(self.format_message(f'acc={self.accel_params}; gyro={self.gyro_params}'))

    def format_message(self, msg: str) -> str:
        return f'Mbient [{self.dev_name}; {self.mac}]: {msg}'

    def register_data_handler(self, handler_fn: 'Mbient.DATA_HANDLER'):
        self.data_handlers.append(handler_fn)

    def prepare_scan(self) -> None:
        """
        Perform a BLE scan to wake up devices before trying to connect.
        (The alternative is to physically push the button on the devices or scan for devices from a Windows computer.)
        We only need to do this once, so this function ensures it is only done once per machine/server.
        """
        with Mbient.SCAN_LOCK:
            if Mbient.SCAN_PERFORMED:  # Only need to scan once if multiple devices are present
                return
            self.logger.debug('Performing BLE Scan')
            ble_devices = scan_BLE(timeout_sec=10)
            self.logger.debug(f'BLE scan found {len(ble_devices)} devices: {[mac for _, mac in ble_devices.items()]}')
            Mbient.SCAN_PERFORMED = True

    def connect(self, n_attempts: Optional[int] = None, retry_delay_sec: Optional[float] = None) -> None:
        """
        Attempt to connect to the device and set a disconnect handler.

        :param n_attempts: How many times to attempt a connection before giving up.
        :param retry_delay_sec: How long to wait in-between attempts.
        """
        if n_attempts is None:
            n_attempts = self.max_connect_attempts
        if retry_delay_sec is None:
            retry_delay_sec = self.retry_delay_sec

        device = connect_device(
            mac_address=self.mac,
            n_attempts=n_attempts,
            retry_delay_sec=retry_delay_sec,
            log_fn=lambda msg: self.logger.debug(self.format_message(msg)),
        )
        self.device_wrapper = MetaWearWrapper.create_wrapper(device)
        self.device_wrapper.on_disconnect = lambda status: self.attempt_reconnect(status)

    def attempt_reconnect(self, status: Optional[int] = None, notify: bool = True, n_attempts: int = 3) -> None:
        """
        Callback for disconnect events. Attempt to reconnect to and configure the device.
        :param status: The status code passed by the callback handler.
        :param notify: Whether to prompt a warning about premature disconnection.
        :param n_attempts: How many reconnection attempts to make.
        """
        t0 = time()
        if notify:
            print(f"-WARNING mbient- {self.dev_name} diconnected prematurely")  # Send message to GUI terminal
            self.logger.warning(self.format_message(f'Disconnected Prematurely (status={status})'))

        self.device_wrapper.on_disconnect = lambda status_: self.logger.info(self.format_message(
            f'Disconnect during attempt_reconnect with status={status_}'
        ))

        try:
            was_streaming = self.streaming
            self.connect(n_attempts=n_attempts, retry_delay_sec=0.5)
            self.setup()
            if was_streaming:
                self.start(buzz=False)
            self.logger.info(self.format_message('Reconnect Completed'))
        except MbientFailedConnection as e:
            print(f"Failed to reconnect {self.dev_name}")  # Send message to GUI terminal
            self.logger.error(self.format_message(f'Failed to Reconnect: {e}'))
        except Exception as e:
            print(f"Couldn't setup for {self.dev_name}")  # Send message to GUI terminal
            self.logger.error(self.format_message(f'Error during reconnect: {e}'), exc_info=sys.exc_info())
        finally:
            self.logger.debug(self.format_message(f'attempt_reconnect took {time() - t0} seconds.'))

    @staticmethod
    def task_start_reconnect(devices: List['Mbient']) -> None:
        """
        Given a list of Mbient devices, attempt reconnection in parallel if any are disconnected.
        :param devices: The devices to check and attempt reconnection on if necessary.
        """
        disconnected_devices = [dev for dev in devices if not dev.device_wrapper.is_connected]
        if len(disconnected_devices) == 0:
            return  # Everything is connected; do nothing

        # Print message to GUI terminal
        device_names = [dev.dev_name for dev in disconnected_devices]
        print(f'The following Mbients are disconnected: {device_names}. Attempting to reconnect...')

        # Attempt reconnection in parallel
        with ThreadPoolExecutor(max_workers=len(disconnected_devices)) as executor:
            results = [
                executor.submit(dev.attempt_reconnect, notify=False, n_attempts=1) for dev in disconnected_devices
            ]
            wait(results)  # Wait for reconnects to complete

        print('Pre-task reconnect attempts complete.')  # Print message to GUI terminal

    def reset(self, timeout_sec: float = 10) -> None:
        """
        Perform a board reset (which disconnects the device).
        This call blocks until the reset is complete or the timeout is reached.

        :param timeout_sec: How long to wait for the disconnect to occur.
        """
        event = mp.Event()

        def disconnect_callback(status):
            self.logger.info(self.format_message('Disconnected during reset'))
            event.set()

        self.logger.info(self.format_message('Resetting Device'))
        self.device_wrapper.on_disconnect = disconnect_callback
        self.device_wrapper.reset_device()
        if not event.wait(timeout=timeout_sec):
            raise MbientResetTimeout('Device reset timed out.')

        # Re-supply a generic disconnect event
        self.device_wrapper.on_disconnect = lambda status: self.logger.info(self.format_message(
            f'Disconnect with status={status}'
        ))

    def reset_and_reconnect(self, timeout_sec: float = 10) -> bool:
        """
        Stop streaming, perform a board reset (which disconnects the device), reconnect, and resume streaming.
        :param timeout_sec: How long to wait for the reset to occur before timing out.
        :return: Whether the device is connected after the function call is complete.
        """
        print(f'Resetting {self.dev_name}.')  # Send message to GUI terminal
        self.logger.info(self.format_message('Resetting'))

        try:
            if not self.device_wrapper.is_connected:  # Attempt to reconnect if previously disconnected
                self.connect()

            was_streaming = self.streaming
            if was_streaming:
                self.stop()

            self.reset(timeout_sec=timeout_sec)
            self.connect()
            self.setup()

            if was_streaming:
                self.start(buzz=False)

            self.logger.info(self.format_message(f'Reset Completed'))
            return self.device_wrapper.is_connected
        except Exception as e:
            self.logger.error(self.format_message(f'Error during reset and reconnect: {e}'))
            return False

    def prepare(self) -> bool:
        """
        Connect to and configure the device.
        :returns: Whether the connection and setup was successful.
        """
        try:
            self.prepare_scan()  # Wake up devices
            self.connect()
            self.logger.debug(self.format_message(f'Device Model: {self.device_wrapper.model_name}'))
            self.logger.debug(self.format_message(f'Wrapper Class: {self.device_wrapper.__class__.__name__}'))

            # Perform a sensor reset and reconnect
            self.reset()
            sleep(self.retry_delay_sec)  # Wait a moment before trying to re-connect after the reset
            self.connect()

            # Set up the device to stream acceleration and angular velocity
            if not DISABLE_LSL:
                self.outlet = self._create_outlet()
            self.setup()
            if not DISABLE_LSL:
                print(f"-OUTLETID-:mbient_{self.dev_name}:{self.outlet_id}")  # Signal to GUI that everything is OK

            return True
        except (MbientFailedConnection, MbientResetTimeout) as e:
            print(f"Failed to connect mbient {self.dev_name}")  # Send message to GUI terminal
            self.logger.error(self.format_message(str(e)))
            return False
        except Exception as e:
            self.logger.error(self.format_message(f'Error during prepare: {e}'), exc_info=sys.exc_info())
            return False

    def _create_outlet(self) -> StreamOutlet:
        """Create an LSL outlet; helper for prepare."""
        stream_mbient = set_stream_description(
            stream_info=StreamInfo(
                name=f"mbient_{self.dev_name}",
                type="acc",
                channel_count=7,
                channel_format="double64",
                source_id=self.outlet_id,
            ),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 1),
            columns=['Time_Mbient', 'AccelX', 'AccelY', 'AccelZ', 'GyroX', 'GyroY', 'GyroZ'],
            column_desc={
                'Time_Mbient': 'Device timestamp (ms; epoch)',
                'AccelX': 'X component of acceleration in local coordinate frame (g)',
                'AccelY': 'Y component of acceleration in local coordinate frame (g)',
                'AccelZ': 'Z component of acceleration in local coordinate frame (g)',
                'GyroX': 'Angular velocity about X axis in local coordinate frame (deg/s)',
                'GyroY': 'Angular velocity about Y axis in local coordinate frame (deg/s)',
                'GyroZ': 'Angular velocity about Z axis in local coordinate frame (deg/s)',
            }
        )
        return StreamOutlet(stream_mbient)

    def _callback(self, context: Any, data: Any) -> None:
        """Process data streamed from the device"""
        self.n_samples_streamed += 1
        acc, gyro = parse_value(data, n_elem=2)
        for handler in self.data_handlers:
            handler(data.contents.epoch, acc, gyro)

    def _lsl_data_handler(self, epoch: float, acc: Any, gyro: Any) -> None:
        """Push data to LSL"""
        self.outlet.push_sample([epoch, acc.x, acc.y, acc.z, gyro.x, gyro.y, gyro.z])

    def setup(self) -> None:
        """Configure the device (i.e., connection settings, sensor settings, data streaming callback)"""
        self.device_wrapper.setup_connection_settings(self.connection_params)
        sensor_signals = self.device_wrapper.setup_sensor_settings(self.accel_params, self.gyro_params)

        # Hard-Learned Note: The callback function needs to "stick around" and be an instance variable.
        # (As opposed to an anonymous lambda or function-scoped variable.)
        # If not, then the program will silently fail when the callback gets triggered.
        # Speculation: Python can garbage collect variables that the C bindings expect to exist => memory access error.
        processor = MetaWearWrapper.create_data_fusion_processor(sensor_signals)
        if DISABLE_LSL:
            self.logger.warning('LSL Disabled!')
        else:
            self.data_handlers = [self._lsl_data_handler, *self.data_handlers]  # Make sure LSL is called first!
        libmetawear.mbl_mw_datasignal_subscribe(processor, None, self.callback)
        self.subscribed_signals.append(processor)

        print(f"Mbient {self.dev_name} setup")  # Send message to GUI terminal
        self.logger.debug(self.format_message('Setup Completed'))

    def log_battery_info(self) -> None:
        """
        Query the device for its battery status and print it to the log.
        """
        battery_state = self.device_wrapper.get_battery_state()
        self.logger.info(self.format_message(
            f'Voltage = {battery_state.voltage / 1e3:.1f} V; Charge = {battery_state.charge}%'
        ))

    def start(self, buzz: bool = False) -> None:
        """Begin streaming data.
        :param buzz: Whether to enable the sensor buzz when stating data capture.
        """
        self.device_wrapper.enable_inertial_sampling()

        if buzz and self.buzz_time:  # Vibrate and then start acquisition
            self.logger.debug(self.format_message(f'Buzz for {self.buzz_time} s'))
            self.device_wrapper.buzz(100, self.buzz_time)

        self.logger.debug(self.format_message('Starting Streaming'))
        self.streaming = True
        self.device_wrapper.start_inertial_sampling()

    def stop(self) -> None:
        """Stop streaming data."""
        self.logger.debug(self.format_message('Stopping Streaming'))
        self.device_wrapper.stop_inertial_sampling()
        self.device_wrapper.disable_inertial_sampling()
        self.streaming = False

    def disconnect(self) -> None:
        """Disconnect the device."""
        self.logger.debug(self.format_message('Disconnecting...'))
        e = mp.Event()
        self.device_wrapper.on_disconnect = lambda status: e.set()
        self.device_wrapper.disconnect()
        if e.wait(timeout=10):
            self.logger.debug(self.format_message('Disconnected'))
        else:
            self.logger.error(self.format_message('Timed Out on Disconnect'))

    def close(self) -> None:
        """Stop streaming data, unsubscribe from data signals, and disconnect the device."""
        try:
            if self.streaming:
                self.stop()

            for signal in self.subscribed_signals:
                libmetawear.mbl_mw_datasignal_unsubscribe(signal)
        except Exception as e:
            self.logger.error(
                self.format_message(f'Unable to stop or unsubscribe from all signals: {e}'),
                exc_info=sys.exc_info()
            )
        finally:
            self.disconnect()


# --------------------------------------------------------------------------------
# Testing Script
# --------------------------------------------------------------------------------
def test_script() -> None:
    """
    Connect to the specified device, print battery status, capture data for some time (printing to the console),
    and then disconnect.
    """
    global DISABLE_LSL
    DISABLE_LSL = True

    parser = argparse.ArgumentParser(description='Run a standalone test data capture using an Mbient.')
    parser.add_argument(
        '--mac',
        required=True,
        type=str,
        help='The MAC address of the device to connect to.'
    )
    parser.add_argument(
        '--name',
        default='Test',
        type=str,
        help='A device name for the logs.'
    )
    parser.add_argument(
        '--duration',
        default=10,
        type=int,
        help='Duration of data capture.'
    )
    parser.add_argument(
        '--decimate',
        default=20,
        type=int,
        help='Only print every Nth received sample to the console.'
    )

    args = parser.parse_args()

    if args.duration < 1:
        parser.error('Invalid duration specified!')
    if args.decimate < 1:
        parser.error('Invalid decimate specified!')

    logger = logging.getLogger(APP_LOG_NAME)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('|%(levelname)s| [%(asctime)s] L%(lineno)d> %(message)s'))
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG)

    logger.info(f'Creating Device {args.name} at {args.mac}')
    dev_args = MbientDeviceArgs()
    device = Mbient(dev_args)
    Mbient.SCAN_PERFORMED = True  # Make repeated runs of test script faster; comment out if needed.

    def _test_data_handler(epoch: float, acc: Any, gyro: Any) -> None:
        """Prints data to the console"""
        if (device.n_samples_streamed - 1) % args.decimate == 0:
            print(f'Epoch={epoch}, Accel={acc}, Gyro={gyro}', flush=True)

    device.register_data_handler(_test_data_handler)
    success = device.prepare()
    if not success:
        logger.critical(f'Unable to connect to device at {args.mac}')
        return

    device.log_battery_info()

    logger.info('Beginning Recording')
    device.start()
    sleep(args.duration)
    device.stop()
    logger.info('Stopped Recording')

    logger.info(f'Received {device.n_samples_streamed} samples.')
    device.close()


if __name__ == "__main__":
    test_script()
