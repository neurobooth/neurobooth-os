# -*- coding: utf-8 -*-
import os
import sys
import argparse
import json
from typing import Dict, List
from mbientlab.metawear import MetaWear, libmetawear
from time import sleep, time
import threading
import logging
from neurobooth_os.iout.mbient import scan_BLE
from neurobooth_os.logging import make_default_logger


DESCRIPTION = """Find and reset Mbient wearable devices.

This script has three modes of device discovery:
    1. Scan: This is the default mode of discovery. The script will scan for nearby BLE devices until it either reaches
    the timeout or finds the specified number of devices with the Metawear GATT service UUID.
    Example (scan for either 10 sec or until 5 devices are found):
        python reset_mbients.py --scan-timeout=10 --n-devices=5
    
    2. MAC via command line: MAC addresses can be specified via the command line using the --mac argument. The argument
    can be specified multiple times to reset multiple devices.
    Example (reset the devices with MAC addresses E8:95:D6:F7:39:D2 and FE:07:3E:37:F5:9C):
        python reset_mbients.py --mac=E8:95:D6:F7:39:D2 --mac=FE:07:3E:37:F5:9C
        
    3. MAC va JSON file: This is simular to discovery mode 2, except it allows each MAC address to be associated with a
    device name. The JSON file should be a dictionary where each key is a device name and each value is the
    corresponding MAC Address.
    Example (reset the devices in device.json):
        python reset_mbients.py --json=device.json
        
        >>>contents of device.json
        {
        "Mbient_LH_2": "E8:95:D6:F7:39:D2",
        "Mbient_RH_2": "FE:07:3E:37:F5:9C",
        "Mbient_RF_2": "E5:F6:FB:6D:11:8A",
        "Mbient_LF_2": "DA:B0:96:E4:7F:A3",
        "Mbient_BK_1": "D7:B0:7E:C2:A1:23"
        }
        <<<
"""


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)

    group = parser.add_argument_group(title='Device Discovery')
    group.add_argument(
        '--n-devices',
        default=5,
        type=int,
        help='The number of expected devices when scanning. (I.e., stop scanning once this many devices are found.)'
    )
    group.add_argument(
        '--scan-timeout',
        default=10,
        type=int,
        help='Specify a timeout (in seconds) for scanning for devices.'
    )
    group.add_argument(
        '--mac',
        default=[],
        required=False,
        action='append',
        type=str,
        help='Instead of scanning for devices, specify the MAC address. '
             'This argument can be specified multiple times to reset multiple devices.'
    )
    group.add_argument(
        '--json',
        default=None,
        type=str,
        help='Instead of scanning for devices, specify a JSON file containing a dictionary '
             'of DEVICE_NAME: MAC_ADDRESS pairs.'
    )

    group = parser.add_argument_group(title='Reset Arguments')
    group.add_argument(
        '--n-connect-attempts',
        default=3,
        type=int,
        help='The number of times to attempt to connect to a device.'
    )
    group.add_argument(
        '--reset-timeout',
        default=10,
        type=int,
        help='Specify a timeout (in seconds) for resetting the devices.'
    )

    args = parser.parse_args()

    if args.scan_timeout <= 0:
        parser.error(f'Invalid scan timeout specified ({args.scan_timeout} sec).')
    if args.reset_timeout <= 0:
        parser.error(f'Invalid reset timeout specified ({args.reset_timeout} sec).')
    if args.n_devices <= 0:
        parser.error(f'Invalid number of devices specified ({args.n_devices}).')
    if args.n_connect_attempts <= 0:
        parser.error(f'Invalid number of connect attempts specified ({args.n_connect_attempts}).')

    return args


class ResetDeviceThread(threading.Thread):
    def __init__(self, address: str, name: str, connect_attempts: int, reset_timeout: float):
        """
        When started, this thread will try to connect to and reset the specified Mbient device.

        :param address: The MAC address of the device to reset.
        :param name: The device's name (for logging).
        :param connect_attempts: The number of times to try to connect to the device before giving up.
        :param reset_timeout: How long to wait for the device to reset before giving up.
        """
        super().__init__()
        self.address = address
        self.name = name
        self.connect_attempts = connect_attempts
        self.reset_timeout = reset_timeout
        self.logger = logging.getLogger('default')
        self.disconnect_event = threading.Event()
        self.success = False

    def format_message(self, msg: str) -> str:
        return f'{self.name} [{self.address}]: {msg}'

    def run(self) -> None:
        t0 = time()
        try:
            device = self.connect()
            ResetDeviceThread.reset_device(device)
            self.success = self.disconnect_event.wait(self.reset_timeout)
        except Exception as e:
            self.logger.exception(e)
        finally:
            if self.success:
                self.logger.debug(self.format_message(f'Reset took {time() - t0:0.1f} sec.'))
            else:
                self.logger.debug(self.format_message(f'Reset timed out!'))

    def connect(self) -> MetaWear:
        """
        Attempt to connect to the device. Raise an exception if the maximum number of attempts is exceeded.

        :returns: The connected Mbient device object.
        """
        device = MetaWear(self.address)

        success = False
        self.logger.debug(self.format_message(f'Attempting Connection'))
        for i in range(self.connect_attempts):
            try:
                if i > 0:  # Do not immediately try to reconnect if it just failed.
                    sleep(3)

                device.connect()
                success = True
                break
            except Exception as e:
                self.logger.debug(self.format_message(f'Failed to connect on attempt {i + 1}: {e}'))

        if not success:
            raise Exception(self.format_message(f'Unable to connect!'))

        device.on_disconnect = lambda status: self.on_disconnect(status)
        return device

    def on_disconnect(self, status) -> None:
        self.logger.debug(self.format_message(f'Disconnected with status {status}.'))
        self.disconnect_event.set()

    @staticmethod
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


ADDRESS_MAP = Dict[str, str]  # Type alias for return of discovery functions


class DeviceDiscoveryException(Exception):
    pass


def device_discovery(args: argparse.Namespace) -> ADDRESS_MAP:
    if args.json is not None:
        devices = discovery_json(args.json)
    elif args.mac:
        devices = discovery_mac(args.mac)
    else:
        devices = discovery_scan(timeout_sec=args.scan_timeout, n_devices=args.n_devices)

    logger = logging.getLogger('default')
    for k, v in devices.items():
        logger.debug(f'Device {k} Address: {v}')

    return devices


def discovery_scan(timeout_sec: float, n_devices: int) -> ADDRESS_MAP:
    logger = logging.getLogger('default')
    logger.info('Scanning for devices...')

    t0 = time()
    devices = scan_BLE(timeout_sec=timeout_sec, n_devices=n_devices)
    logger.info(f'Scan took {time() - t0:0.1f} sec.')

    if len(devices) == 0:
        raise DeviceDiscoveryException('No devices found!')
    elif len(devices) < n_devices:
        logger.warning(f'Only {len(devices)} of {n_devices} devices found!')
    else:
        logger.info(f'Scan identified {len(devices)} devices.')

    return devices


def discovery_mac(addresses: List[str]) -> ADDRESS_MAP:
    logger = logging.getLogger('default')
    devices = {f'CL-{i}': address for i, address in enumerate(addresses)}
    logger.info(f'Using {len(devices)} devices specified via command line.')
    return devices


def discovery_json(file: str) -> ADDRESS_MAP:
    logger = logging.getLogger('default')

    with open(file, 'r') as f:
        devices = json.load(f)

    # File validation checks
    if not isinstance(devices, dict):
        raise DeviceDiscoveryException(f'{file} should contain a dictionary mapping device names to MAC addresses.')
    if len(devices) == 0:
        raise DeviceDiscoveryException(f'No devices specified in {file}!')
    for k, v in devices.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise DeviceDiscoveryException(f'{file} should contain a dictionary mapping device names to MAC addresses.')

    logger.info(f'Using {len(devices)} devices specified in: {file}')
    return devices


def reset_devices(args: argparse.Namespace, devices: ADDRESS_MAP) -> None:
    reset_threads = [
        ResetDeviceThread(
            address=address,
            name=name,
            connect_attempts=args.n_connect_attempts,
            reset_timeout=args.reset_timeout,
        ) for name, address in devices.items()
    ]

    logger = logging.getLogger('default')
    logger.info(f'Reset in progress...')
    t0 = time()
    for t in reset_threads:
        t.start()
    for t in reset_threads:
        t.join()
    logger.info(f'Device reset {time() - t0:0.1f} sec.')

    success = [t.address for t in reset_threads if t.success]
    failure = [t.address for t in reset_threads if not t.success]
    logger.info(f'Succesfully reset {len(success)} devices: {success}')
    if failure:
        logger.warning(f'Failed to reset {len(failure)} devices: {failure}')


def main():
    logger = make_default_logger()
    try:
        args = parse_arguments()
        devices = device_discovery(args)
        reset_devices(args, devices)
    except DeviceDiscoveryException as e:
        logger.exception(e)
        raise e
    except Exception as e:
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        raise e


if __name__ == "__main__":
    main()
