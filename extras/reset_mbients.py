# -*- coding: utf-8 -*-
import sys
import argparse
import json
from typing import Callable, List, NamedTuple
from time import time
import multiprocessing as mp
import logging
from neurobooth_os.iout.mbient import scan_BLE, connect_device, reset_device, MbientFailedConnection
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


class DeviceInfo(NamedTuple):
    name: str
    address: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION, formatter_class=argparse.RawDescriptionHelpFormatter)

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


ADDRESS_MAP = List[DeviceInfo]  # Type alias for return of discovery functions


def print_device_info(devices: List[DeviceInfo], print_fn: Callable[[str], None] = print) -> None:
    """Convenience function for logging/printing a list of devices and their addresses"""
    for d in devices:
        print_fn(f'Device {d.name}: {d.address}')


class DeviceDiscoveryException(Exception):
    pass


def device_discovery(args: argparse.Namespace) -> ADDRESS_MAP:
    # Need to do a scan no matter what to wake up the devices
    devices = discovery_scan(timeout_sec=args.scan_timeout, n_devices=args.n_devices)

    # Override devices if specified by command line
    if args.json is not None:
        devices = discovery_json(args.json)
    elif args.mac:
        devices = discovery_mac(args.mac)

    logger = logging.getLogger('default')
    logger.debug(f'Devices:')
    print_device_info(devices, print_fn=logger.debug)

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

    return [DeviceInfo(name=name, address=address) for name, address in devices.items()]


def discovery_mac(addresses: List[str]) -> ADDRESS_MAP:
    logger = logging.getLogger('default')
    devices = [DeviceInfo(name=f'CL-{i}', address=address) for i, address in enumerate(addresses)]
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
    return [DeviceInfo(name=name, address=address) for name, address in devices.items()]


class ResetDeviceProcess(mp.Process):
    def __init__(self, device_info: DeviceInfo, connect_attempts: int, reset_timeout: float):
        """
        When started, this process will try to connect to and reset the specified Mbient device.

        :param device_info: The name and address of the device to reset.
        :param connect_attempts: The number of times to try to connect to the device before giving up.
        :param reset_timeout: How long to wait for the device to reset before giving up.
        """
        super().__init__(target=self.run)
        self.device_info = device_info
        self.connect_attempts = connect_attempts
        self.reset_timeout = reset_timeout

        manager = mp.Manager()
        self.disconnect_event = manager.Event()
        self.namespace = manager.Namespace()  # Used to pass variables between processes
        self.namespace.success = False

    def format_message(self, msg: str) -> str:
        return f'{self.device_info.name} <{self.device_info.address}>: {msg}'

    def run(self) -> None:
        logger = make_default_logger()
        t0 = time()
        try:
            device = connect_device(
                mac_address=self.device_info.address,
                n_attempts=self.connect_attempts,
                retry_delay_sec=3,
                log_fn=lambda msg: logger.debug(self.format_message(msg))
            )
            device.on_disconnect = lambda status: self.on_disconnect(status)
            reset_device(device)
            self.namespace.success = self.disconnect_event.wait(self.reset_timeout)
        except MbientFailedConnection as e:
            logger.error(self.format_message(str(e)))
        except Exception as e:
            logger.exception(e)
        finally:
            if self.namespace.success:
                logger.debug(self.format_message(f'Reset took {time() - t0:0.1f} sec.'))
            else:
                logger.debug(self.format_message(f'Reset timed out!'))

    def on_disconnect(self, status) -> None:
        logging.getLogger('default').debug(self.format_message(f'Disconnected with status {status}.'))
        self.disconnect_event.set()

    @property
    def success(self) -> bool:
        return self.namespace.success


def reset_devices(args: argparse.Namespace, devices: ADDRESS_MAP) -> (ADDRESS_MAP, ADDRESS_MAP):
    """
    Connect to and reset all devices in parallel.

    :param args: Command line arguments.
    :param devices: The list of devices (name and MAC address) to connect to and reset.
    :returns: (success, failure): Lists of which devices were successfully reset and which were not.

    """
    reset_processes = [
        ResetDeviceProcess(
            device_info=device,
            connect_attempts=args.n_connect_attempts,
            reset_timeout=args.reset_timeout,
        ) for device in devices
    ]

    logger = logging.getLogger('default')
    logger.info(f'Reset in progress...')
    t0 = time()
    for t in reset_processes:
        t.start()
    for t in reset_processes:
        t.join()
    logger.info(f'Device reset {time() - t0:0.1f} sec.')

    success = [t.device_info for t in reset_processes if t.success]
    failure = [t.device_info for t in reset_processes if not t.success]
    return success, failure


def main():
    logger = make_default_logger()
    try:
        args = parse_arguments()
        devices = device_discovery(args)
        success, failure = reset_devices(args, devices)

        logger.info(f'Successfully reset {len(success)} devices:')
        print_device_info(success, print_fn=logger.info)
        if failure:
            logger.warning(f'Failed to reset {len(failure)} devices:')
            print_device_info(failure, print_fn=logger.warning)
    except DeviceDiscoveryException as e:
        logger.exception(e)
        raise e
    except Exception as e:
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        raise e


if __name__ == "__main__":
    main()
