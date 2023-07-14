import sys
import argparse
import uuid
from ctypes import c_void_p, cast, POINTER
from time import sleep
import multiprocessing as mp
import logging
from typing import Any, Dict, List, Callable, NamedTuple, Optional

from mbientlab.warble import BleScanner
from mbientlab.metawear import MetaWear, libmetawear, parse_value, cbindings


# --------------------------------------------------------------------------------
# Module-level constants and debugging flags
# --------------------------------------------------------------------------------
DISABLE_LSL: bool = False  # If True, LSL streams will not be created nor will received data be pushed.
if not DISABLE_LSL:  # Conditional imports based on flags
    from pylsl import StreamInfo, StreamOutlet
    from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description

DEBUG_PRINT_DATA: bool = False  # If True and LSL is disabled, print every 100th data point to the console.


# --------------------------------------------------------------------------------
# Exception Classes
# --------------------------------------------------------------------------------
class MbientError(Exception):
    pass


class MbientFailedConnection(MbientError):
    pass


# --------------------------------------------------------------------------------
# Procedural Interface for External Scripts
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


class ConnectionParameters(NamedTuple):
    """
    Arguments for mbl_mw_settings_set_connection_parameters
    See: https://mbientlab.com/documents/metawear/cpp/latest/settings_8h.html#a1cf3cae052fe7981c26124340a41d66d
    """
    min_conn_interval: float = 7.5
    max_conn_interval: float = 7.5
    latency: int = 0
    timeout: int = 6000


def setup_connection_settings(device: MetaWear, connection_params: ConnectionParameters) -> None:
    """
    Configure the connection settings and transmission power.
    See: https://mbientlab.com/documents/metawear/cpp/latest/settings_8h.html#a1cf3cae052fe7981c26124340a41d66d
    See: https://mbientlab.com/documents/metawear/cpp/latest/settings_8h.html#a335f712d5fc0587eff9671b8b105d3ed

    :param device: The device to update.
    :param connection_params: Arguments for mbl_mw_settings_set_connection_parameters.
    """
    board = device.board
    libmetawear.mbl_mw_settings_set_connection_parameters(
        board,
        connection_params.min_conn_interval,
        connection_params.max_conn_interval,
        connection_params.latency,
        connection_params.timeout,
    )
    libmetawear.mbl_mw_settings_set_tx_power(board, 8)
    sleep(1)


class SensorParameters(NamedTuple):
    """
    Generic parameters for a sensor.
    See: https://mbientlab.com/documents/metawear/cpp/latest/accelerometer_8h.html#a5b7609e6a950d87215be8bea52ffe48c
    See: https://mbientlab.com/documents/metawear/cpp/latest/gyro__bosch_8h.html#ab6c0e565c919ee7ccb859d03e06b29d5
    """
    sample_rate: float  # Hz; anything beyond 100 may not work well
    data_range: float  # gs for accelerometer, degrees per second for gyroscope


class SensorSignals(NamedTuple):
    """The data signal objects for each onboard sensor."""
    accel_signal: Any
    gyro_signal: Any


def setup_sensor_settings(
        device: MetaWear,
        accel_params: SensorParameters,
        gyro_params: SensorParameters,
) -> SensorSignals:
    """
    Configure the settings of the accelerometer and gyroscope.
    See: https://mbientlab.com/documents/metawear/cpp/latest/accelerometer_8h.html
    See: https://mbientlab.com/documents/metawear/cpp/latest/gyro__bosch_8h.html

    :param device: The device to update.
    :param accel_params: Settings for the accelerometer.
    :param gyro_params: Settings for the gyroscope.
    :returns: A NamedTuple containing the signal objects for the accelerometer and gyroscope.
    """
    board = device.board
    # Configure accelerometer
    libmetawear.mbl_mw_acc_set_odr(board, accel_params.sample_rate)
    libmetawear.mbl_mw_acc_set_range(board, accel_params.data_range)
    libmetawear.mbl_mw_acc_write_acceleration_config(board)

    # Configure gyroscope
    try:  # MMRS only
        libmetawear.mbl_mw_gyro_bmi270_set_odr(board, gyro_params.sample_rate)
        libmetawear.mbl_mw_gyro_bmi270_set_range(board, gyro_params.data_range)
        libmetawear.mbl_mw_gyro_bmi270_write_config(board)
    except:  # MMR1, MMR and MMC only
        libmetawear.mbl_mw_gyro_bmi160_set_odr(board, gyro_params.sample_rate)
        libmetawear.mbl_mw_gyro_bmi160_set_range(board, gyro_params.data_range)
        libmetawear.mbl_mw_gyro_bmi160_write_config(board)

    acc = libmetawear.mbl_mw_acc_get_acceleration_data_signal(board)
    try:  # MMRS only
        gyro = libmetawear.mbl_mw_gyro_bmi270_get_rotation_data_signal(board)
    except:  # MMR1, MMR and MMC only
        gyro = libmetawear.mbl_mw_gyro_bmi160_get_rotation_data_signal(board)

    return SensorSignals(accel_signal=acc, gyro_signal=gyro)


class DataFusionCreator:
    """Helper class for creating a data fusion processor.
    The class provides a limited scope for the callback and event variable needed to wait for the response.
    See: https://github.com/mbientlab/MetaWear-SDK-Python/blob/master/examples/data_processor.py
    """
    def __init__(self):
        self.processor_created = mp.Event()
        self.processor = None

    def _processor_created_callback(self, context, pointer):
        self.processor = pointer
        self.processor_created.set()

    def create_processor(self, sensor_signals: SensorSignals):
        """
        Create a data processor that fuses the accelerometer and gyroscope signals.

        :param sensor_signals: A NamedTuple containing the signal objects for the accelerometer and gyroscope.
        :returns: The data processor object that scan be subscribed to.
        """
        signals = (c_void_p * 1)()
        signals[0] = sensor_signals.gyro_signal

        callback = cbindings.FnVoid_VoidP_VoidP(self._processor_created_callback)
        libmetawear.mbl_mw_dataprocessor_fuser_create(sensor_signals.accel_signal, signals, 1, None, callback)
        self.processor_created.wait()

        return self.processor


def enable_inertial_sampling(device: MetaWear) -> None:
    """
    Enable sampling on the accelerometer and gyroscope.
    :param device: The device to update.
    """
    board = device.board
    libmetawear.mbl_mw_acc_enable_acceleration_sampling(board)
    try:  # MMRS only
        libmetawear.mbl_mw_gyro_bmi270_enable_rotation_sampling(board)
    except:  # MMR1, MMR and MMC only
        libmetawear.mbl_mw_gyro_bmi160_enable_rotation_sampling(board)


def disable_inertial_sampling(device: MetaWear) -> None:
    """
    Disable sampling on the accelerometer and gyroscope.
    :param device: The device to update.
    """
    board = device.board
    libmetawear.mbl_mw_acc_disable_acceleration_sampling(board)
    try:  # MMRS only
        libmetawear.mbl_mw_gyro_bmi270_disable_rotation_sampling(board)
    except:  # MMR1, MMR and MMC only
        libmetawear.mbl_mw_gyro_bmi160_disable_rotation_sampling(board)


def start_inertial_sampling(device: MetaWear) -> None:
    """
    Start sampling on the accelerometer and gyroscope.
    :param device: The device to update.
    """
    board = device.board
    libmetawear.mbl_mw_acc_start(board)
    try:  # MMRS only
        libmetawear.mbl_mw_gyro_bmi270_start(board)
    except:  # MMR1, MMR and MMC only
        libmetawear.mbl_mw_gyro_bmi160_start(board)


def stop_inertial_sampling(device: MetaWear) -> None:
    """
    Stop sampling on the accelerometer and gyroscope.
    :param device: The device to update.
    """
    board = device.board
    libmetawear.mbl_mw_acc_stop(board)
    try:  # MMRS only
        libmetawear.mbl_mw_gyro_bmi270_stop(board)
    except:  # MMR1, MMR and MMC only
        libmetawear.mbl_mw_gyro_bmi160_stop(board)


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

    def __init__(
        self,
        mac: str,
        dev_name: str = "mbient",
        device_id: str = "mbient",
        sensor_ids: List[str] = ("acc", "gyro"),
        acc_hz: int = 100,
        gyro_hz: int = 100,
        buzz_time_sec: float = 0,
        try_nmax: int = 5,
    ):
        self.mac = mac
        self.dev_name = dev_name
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self.outlet_id = str(uuid.uuid4())
        self.buzz_time = buzz_time_sec
        self.max_connect_attempts = try_nmax

        # Device configuration settings
        self.connection_params = ConnectionParameters()  # Use the default params
        self.accel_params = SensorParameters(sample_rate=acc_hz, data_range=16.0)
        self.gyro_params = SensorParameters(sample_rate=gyro_hz, data_range=2000)

        # Uninitialized Variables
        self.device: Optional[MetaWear] = None
        self.subscribed_signals: List[Any] = []
        self.outlet: Optional[StreamOutlet] = None
        self.callback: Callable = lambda *args: None

        # Streaming-related variables
        self.streaming: bool = False
        self.n_samples_streamed = 0

        self.logger = logging.getLogger('session')
        self.logger.debug(self.format_message(f'acc={self.accel_params}; gyro={self.gyro_params}'))

    def format_message(self, msg: str) -> str:
        return f'Mbient [{self.dev_name}; {self.mac}]: {msg}'

    def prepare_scan(self) -> None:
        """
        Perform a BLE scan to wake up devices before trying to connect.
        (The alternative is to physically push the button on the devices.)
        We only need to do this once, so this function ensures it is only done once per machine/server.
        """
        with self.SCAN_LOCK:
            if self.SCAN_PERFORMED:  # Only need to scan once if multiple devices are present
                return
            self.logger.debug('Performing BLE Scan')
            ble_devices = scan_BLE(timeout_sec=10)
            self.logger.debug(f'BLE scan found {len(ble_devices)} devices: {[mac for _, mac in ble_devices.items()]}')
            self.SCAN_PERFORMED = True

    def connect(self, n_attempts: int, retry_delay_sec: float) -> None:
        """
        Attempt to connect to the device and set a disconnect handler.

        :param n_attempts: How many times to attempt a connection before giving up.
        :param retry_delay_sec: How long to wait in-between attempts.
        """
        self.device = connect_device(
            mac_address=self.mac,
            n_attempts=n_attempts,
            retry_delay_sec=retry_delay_sec,
            log_fn=lambda msg: self.logger.debug(self.format_message(msg)),
        )
        self.device.on_disconnect = lambda status: self.on_disconnect(status)

    def on_disconnect(self, status=None) -> None:
        """
        Callback for disconnect events. Attempt to reconnect to and configure the device.
        :param status: The status code passed by the callback handler.
        """
        print(f"-WARNING mbient- {self.dev_name} diconnected prematurely")
        self.logger.warning(self.format_message(f'Disconnected Prematurely (status={status})'))

        try:
            self.connect(n_attempts=3, retry_delay_sec=0.5)
            self._setup()
        except MbientFailedConnection as e:
            print(f"Failed to reconnect {self.dev_name}... bye")
            self.logger.error(self.format_message(f'Failed to Reconnect: {e}'))
        except Exception as e:
            print(f"Couldn't setup for {self.dev_name}")
            self.logger.error(self.format_message(f'Error during reconnect: {e}'), exc_info=sys.exc_info())

    def prepare(self) -> bool:
        """
        Connect to and configure the device.
        :returns: Whether the connection and setup was successful.
        """
        try:
            self.prepare_scan()  # Wake up devices
            self.connect(n_attempts=self.max_connect_attempts, retry_delay_sec=1)

            # TODO: attempt a device reset and reconnect

            if not DISABLE_LSL:
                self.outlet = self._create_outlet()
            self._setup()
            if not DISABLE_LSL:
                print(f"-OUTLETID-:mbient_{self.dev_name}:{self.outlet_id}")  # Signal to GUI that everything is OK

            return True
        except MbientFailedConnection as e:
            print(f"Failed to connect mbient {self.dev_name}")
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
            data_version=DataVersion(1, 0),
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

    def _lsl_data_handler(self, ctx, data) -> None:
        """Callback to push data to LSL"""
        values = parse_value(data, n_elem=2)
        self.outlet.push_sample([
            data.contents.epoch,
            values[0].x,
            values[0].y,
            values[0].z,
            values[1].x,
            values[1].y,
            values[1].z,
        ])
        self.n_samples_streamed += 1

    def _debug_data_handler(self, ctx, data) -> None:
        """Callback for debugging; may print data to the console."""
        values = parse_value(data, n_elem=2)
        if DEBUG_PRINT_DATA and (self.n_samples_streamed % 100) == 0:
            print(f'Epoch={data.contents.epoch}, Accel={values[0]}, Gyro={values[1]}', flush=True)
        self.n_samples_streamed += 1

    def _setup(self) -> None:
        """Configure the device (i.e., connection settings, sensor settings, data streaming callback)"""
        setup_connection_settings(self.device, self.connection_params)
        sensor_signals = setup_sensor_settings(self.device, self.accel_params, self.gyro_params)

        processor = DataFusionCreator().create_processor(sensor_signals)
        if DISABLE_LSL:
            self.logger.warning('Using Debugging Data Handler')
            self.callback = cbindings.FnVoid_VoidP_DataP(self._debug_data_handler)
        else:
            self.callback = cbindings.FnVoid_VoidP_DataP(self._lsl_data_handler)
        libmetawear.mbl_mw_datasignal_subscribe(processor, None, self.callback)
        self.subscribed_signals.append(processor)

        print(f"Mbient {self.dev_name} setup")
        self.logger.debug(self.format_message('Setup Completed'))

    def log_battery_info(self) -> None:
        """Query the device for its battery status and print it to the log."""
        callback_event = mp.Event()

        def callback(ctx, data):
            value = parse_value(data, n_elem=1)
            self.logger.info(self.format_message(f'Voltage={value.voltage} mV; Charge={value.charge}%'))
            callback_event.set()
        callback = cbindings.FnVoid_VoidP_DataP(callback)

        signal = libmetawear.mbl_mw_settings_get_battery_state_data_signal(self.device.board)
        libmetawear.mbl_mw_datasignal_subscribe(signal, None, callback)
        callback_event.wait()
        libmetawear.mbl_mw_datasignal_unsubscribe(signal)

    def start(self) -> None:
        """Begin streaming data."""
        enable_inertial_sampling(self.device)

        if self.buzz_time:  # Vibrate and then start acquisition
            self.logger.debug(self.format_message(f'Buzz for {self.buzz_time} s'))
            libmetawear.mbl_mw_haptic_start_motor(self.device.board, 100.0, self.buzz_time*1e3)
            sleep(self.buzz_time)

        self.logger.debug(self.format_message('Starting Streaming'))
        self.streaming = True
        start_inertial_sampling(self.device)

    def stop(self) -> None:
        """Stop streaming data."""
        self.logger.debug(self.format_message('Stopping Streaming'))
        stop_inertial_sampling(self.device)
        disable_inertial_sampling(self.device)
        self.streaming = False

    def disconnect(self) -> None:
        """Disconnect the device."""
        self.logger.debug(self.format_message('Disconnecting...'))
        e = mp.Event()
        self.device.on_disconnect = lambda status: e.set()
        self.device.disconnect()
        if e.wait(10):
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
    global DISABLE_LSL, DEBUG_PRINT_DATA
    DISABLE_LSL = True
    DEBUG_PRINT_DATA = False

    parser = argparse.ArgumentParser(description='Run a standalone test capture using an Mbient.')
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

    args = parser.parse_args()

    if args.duration < 1:
        parser.error('Invalid duration specified!')

    logger = logging.getLogger('session')
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter('|%(levelname)s| [%(asctime)s] L%(lineno)d> %(message)s'))
    logger.addHandler(console_handler)
    logger.setLevel(logging.DEBUG)

    logger.info(f'Creating Device {args.name} at {args.mac}')
    device = Mbient(mac=args.mac, dev_name=args.name)
    device.SCAN_PERFORMED = True  # Make repeated runs of test scrip faster; comment out if needed.
    success = device.prepare()
    if not success:
        logger.critical(f'Unable to connect to device at {args.mac}')
        return

    # device.log_battery_info()

    logger.info('Beginning Recording')
    device.start()
    sleep(args.duration)
    device.stop()
    logger.info('Stopped Recording')

    logger.info(f'Received {device.n_samples_streamed} samples.')
    device.close()


if __name__ == "__main__":
    test_script()
