# usage: python data_fuser.py [mac1] [mac2] ... [mac(n)]
from __future__ import print_function
import uuid
from ctypes import c_void_p, cast, POINTER
from time import sleep
from threading import Event, Lock
import multiprocessing as mp
import logging
from typing import Dict, Callable

from mbientlab.warble import BleScanner
from mbientlab.metawear import MetaWear, libmetawear, parse_value, cbindings
from pylsl import StreamInfo, StreamOutlet, local_clock

from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


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

    return device


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


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


# --------------------------------------------------------------------------------
# Object-Oriented Interface for Neurobooth-OS
# --------------------------------------------------------------------------------
class Sensor:
    def __init__(
        self,
        mac,
        dev_name="mbient",
        device_id="mbient",
        sensor_ids=["acc", "gyro"],
        acc_hz=100,
        gyro_hz=100,
        buzz_time_sec=0,
    ):

        self.mac = mac
        self.dev_name = dev_name
        self.connector = MetaWear
        self.connect()

        self.processor = None
        self.streaming = False
        self.buzz_time = buzz_time_sec * 1000
        self.acc_hz = acc_hz
        self.gyro_hz = gyro_hz
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self.nsmpl = 0
        self.setup()
        print(f"-OUTLETID-:mbient_{self.dev_name}:{self.oulet_id}")

        self.logger = logging.getLogger('session')
        self.logger.debug(f'Mbient [{self.dev_name}]: acc_sample_rate={self.acc_hz}; gyro_sample_rate={self.gyro_hz}')

    def createOutlet(self):
        # Setup outlet stream infos
        self.oulet_id = str(uuid.uuid4())
        self.stream_mbient = set_stream_description(
            stream_info=StreamInfo(
                name=f"mbient_{self.dev_name}",
                type="acc",
                channel_count=7,
                channel_format="double64",
                source_id=self.oulet_id,
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
        return StreamOutlet(self.stream_mbient)

    def connect(self):
        self.device = self.connector(self.mac)
        self.device.connect()
        self.device.on_disconnect = lambda status: self.try_reconnect(
            message=f"-WARNING mbient- {self.dev_name} diconnected prematurely"
        )

    def try_reconnect(self, time_wait=0.5, message=None):

        if message is None:
            print(f"WARNING {self.dev_name} is diconnected prematurely")
        else:
            print(message)
        self.logger.warning(f'Mbient [{self.dev_name}]: Disconnected Prematurely')

        try:
            self.connect()
        except:
            print(f"Failed to reconnect {self.dev_name}, trying in {time_wait}")
            countdown(time_wait)
            try:
                self.connect()
            except:
                print(f"Failed to reconnect {self.dev_name}... bye")
                self.logger.warning(f'Mbient [{self.dev_name}]: Failed to Reconnect')

        isconn = self.device.is_connected
        if isconn:
            try:
                self.setup(create_outlet=False)
            except:
                print(f"Couldn't setup for {self.dev_name}")
                self.logger.warning(f'Mbient [{self.dev_name}]: Could not Setup')
        return isconn

    def data_handler(self, ctx, data):
        values = parse_value(data, n_elem=2)
        vals = [
            data.contents.epoch,
            values[0].x,
            values[0].y,
            values[0].z,
            values[1].x,
            values[1].y,
            values[1].z,
        ]

        self.outlet.push_sample(vals)
        self.nsmpl += 1

    def setup(self, create_outlet=True):
        libmetawear.mbl_mw_settings_set_connection_parameters(
            self.device.board, 7.5, 7.5, 0, 6000
        )
        libmetawear.mbl_mw_settings_set_tx_power(self.device.board, 8)
        tx = libmetawear.mbl_mw_settings_get_power_status_data_signal(self.device.board)
        print(tx)
        sleep(1)

        libmetawear.mbl_mw_acc_set_odr(self.device.board, self.acc_hz)
        libmetawear.mbl_mw_acc_set_range(self.device.board, 16.0)
        libmetawear.mbl_mw_acc_write_acceleration_config(self.device.board)

        try:  # MMRS only
            libmetawear.mbl_mw_gyro_bmi270_set_odr(self.device.board, self.gyro_hz)
            libmetawear.mbl_mw_gyro_bmi270_set_range(self.device.board, 2000)
            libmetawear.mbl_mw_gyro_bmi270_write_config(self.device.board)
        except:  # MMR1, MMR and MMC only
            libmetawear.mbl_mw_gyro_bmi160_set_odr(self.device.board, self.gyro_hz)
            libmetawear.mbl_mw_gyro_bmi160_set_range(self.device.board, 2000)
            libmetawear.mbl_mw_gyro_bmi160_write_config(self.device.board)

        e = Event()

        def processor_created(context, pointer):
            self.processor = pointer
            e.set()

        fn_wrapper = cbindings.FnVoid_VoidP_VoidP(processor_created)

        if create_outlet:
            self.outlet = self.createOutlet()

        self.callback = cbindings.FnVoid_VoidP_DataP(self.data_handler)

        acc = libmetawear.mbl_mw_acc_get_acceleration_data_signal(self.device.board)

        try:  # MMRS only
            gyro = libmetawear.mbl_mw_gyro_bmi270_get_rotation_data_signal(
                self.device.board
            )
        except:  # MMR1, MMR and MMC only
            gyro = libmetawear.mbl_mw_gyro_bmi160_get_rotation_data_signal(
                self.device.board
            )

        signals = (c_void_p * 1)()
        signals[0] = gyro
        libmetawear.mbl_mw_dataprocessor_fuser_create(acc, signals, 1, None, fn_wrapper)
        e.wait()

        libmetawear.mbl_mw_datasignal_subscribe(self.processor, None, self.callback)

        print(f"Mbient {self.dev_name} setup")

    def info(self):

        dev_info = self.device.info

        def battery_handler(self, ctx, data):
            value = parse_value(data, n_elem=1)
            print("Voltage: {0}, Charge: {1}".format(value.voltage, value.charge))

        signal = libmetawear.mbl_mw_settings_get_battery_state_data_signal(
            self.device.board
        )

        voltage = libmetawear.mbl_mw_datasignal_get_component(
            signal, cbindings.Const.SETTINGS_BATTERY_VOLTAGE_INDEX
        )
        charge = libmetawear.mbl_mw_datasignal_get_component(
            signal, cbindings.Const.SETTINGS_BATTERY_CHARGE_INDEX
        )

        libmetawear.mbl_mw_datasignal_subscribe(charge, None, battery_handler)

    def start(self):
        # print(f"Started mbient{self.dev_name}")
        libmetawear.mbl_mw_acc_enable_acceleration_sampling(self.device.board)
        try:  # MMRS only
            libmetawear.mbl_mw_gyro_bmi270_enable_rotation_sampling(self.device.board)
        except:  # MMR1, MMR and MMC only
            libmetawear.mbl_mw_gyro_bmi160_enable_rotation_sampling(self.device.board)

        # Vibrate for 7 secs and then start aqc
        if self.buzz_time:
            libmetawear.mbl_mw_haptic_start_motor(
                self.device.board, 100.0, self.buzz_time
            )
            sleep(self.buzz_time / 1000)

        # print ("Acquisition started")
        self.logger.debug(f'Mbient [{self.dev_name}]: Starting Streaming')
        self.streaming = True
        libmetawear.mbl_mw_acc_start(self.device.board)
        try:  # MMRS only
            libmetawear.mbl_mw_gyro_bmi270_start(self.device.board)
        except:  # MMR1, MMR and MMC only
            libmetawear.mbl_mw_gyro_bmi160_start(self.device.board)

    def stop(self):
        self.logger.debug(f'Mbient [{self.dev_name}]: Stopping Streaming...')
        e = Event()
        self.device.on_disconnect = lambda status: e.set()
        self.device.disconnect()
        # libmetawear.mbl_mw_debug_reset(self.device.board)
        print("Stopped ", self.dev_name)
        self.streaming = False
        e.wait(10)
        self.logger.debug(f'Mbient [{self.dev_name}]: Streaming Stopped')
        print(self.dev_name, self.nsmpl)

    def close(self):
        self.stop()


def reset_mbient(mac, dev_name="mbient"):
    # connect
    device = MetaWear(mac)
    device.connect()
    print(
        f"Connected to {device.address} {dev_name} over "
        + ("USB" if device.usb.is_connected else "BLE")
    )

    # stop logging
    libmetawear.mbl_mw_logging_stop(device.board)
    sleep(1.0)

    # flush cache if mms
    libmetawear.mbl_mw_logging_flush_page(device.board)
    sleep(1.0)

    # clear logger
    libmetawear.mbl_mw_logging_clear_entries(device.board)
    sleep(1.0)

    # remove events
    libmetawear.mbl_mw_event_remove_all(device.board)
    sleep(1.0)

    # erase macros
    libmetawear.mbl_mw_macro_erase_all(device.board)
    sleep(1.0)

    # debug and garbage collect
    libmetawear.mbl_mw_debug_reset_after_gc(device.board)
    sleep(1.0)

    # delete timer and processors
    libmetawear.mbl_mw_debug_disconnect(device.board)
    sleep(1.0)

    libmetawear.mbl_mw_debug_disconnect(device.board)
    sleep(1.0)

    device.disconnect()
    print(f"{dev_name} reset and disconnected")
    logging.getLogger('session').info(f'Mbient [{dev_name}]: Reset and Disconnected')
    sleep(1.0)


if __name__ == "__main__":
    import numpy as np

    mbients = {
        "LF": "DA:B0:96:E4:7F:A3",
        "LH": "E8:95:D6:F7:39:D2",
        "RF": "E5:F6:FB:6D:11:8A",
        "RH": "FE:07:3E:37:F5:9C",
        "BK": "D7:B0:7E:C2:A1:23",
    }

    macs = ["E5:F6:FB:6D:11:8A"]
    macs = [mbients["LH"]]  # ,mbients["RF"]]#0-, mbients["RF"],  mbients["RH"]]
    mbts = []

    for mac in macs:
        sleep(1.0)
        mbt = Sensor(mac)

        mbts.append(mbt)
    ss
    for mac in macs:
        mbt.start()

    print("recording...")
    sleep(30)
    print("finished recording...")

    for mbt in mbts:
        mbt.stop()

    for s in mbts:
        print(f"num samples:{s.nsmpl}")
        # print(f"num samples:{len(s.nsmpl)}, Fps median:{int(np.median(1/np.diff(s.nsmpl)))}, mean:{int(np.mean(1/np.diff(s.nsmpl)))}")

    # sleep(1)
    # mbt.close()

    # self = Sensor(mac)

    # def data_handler(ctx, data):
    #     values = parse_value(data)
    #     print(values)

    # callback = cbindings.FnVoid_VoidP_DataP(data_handler)

    # signal = libmetawear.mbl_mw_settings_get_battery_state_data_signal(self.device.board)
    # libmetawear.mbl_mw_datasignal_subscribe(signal, None, callback)
    # libmetawear.mbl_mw_datasignal_read(signal)

    # voltage = libmetawear.mbl_mw_datasignal_get_component(signal, cbindings.Const.SETTINGS_BATTERY_VOLTAGE_INDEX)
    # charge = libmetawear.mbl_mw_datasignal_get_component(signal, cbindings.Const.SETTINGS_BATTERY_CHARGE_INDEX)

    # libmetawear.mbl_mw_datasignal_subscribe(voltage, None, callback)
    # libmetawear.mbl_mw_datasignal_subscribe(charge, None, callback)

    # libmetawear.mbl_mw_datasignal_read(voltage)
    # libmetawear.mbl_mw_datasignal_read(charge)

    # self.close()
