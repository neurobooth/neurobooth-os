# -*- coding: utf-8 -*-
import sys
import argparse
from mbientlab.metawear import MetaWear, libmetawear
from time import sleep, time
import threading
import logging
from neurobooth_os.iout.mbient import scan_BLE
from neurobooth_os.logging import make_default_logger


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Find and reset Mbient wearable devices.')

    group = parser.add_argument_group(title='Scanning Arguments')
    group.add_argument(
        '--n-devices',
        default=5,
        type=int,
        help='The number of expected devices'
    )
    group.add_argument(
        '--scan-timeout',
        default=10,
        type=int,
        help='Specify a timeout (in seconds) for identifying the devices.'
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
    def __init__(self, address: str, connect_attempts: int, reset_timeout: float):
        """
        When started, this thread will try to connect to and reset the specified Mbient device.

        :param address: The MAC address of the device to reset.
        :param connect_attempts: The number of times to try to connect to the device before giving up.
        :param reset_timeout: How long to wait for the device to reset before giving up.
        """
        super().__init__()
        self.address = address
        self.connect_attempts = connect_attempts
        self.reset_timeout = reset_timeout
        self.logger = logging.getLogger('default')
        self.disconnect_event = threading.Event()
        self.success = False

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
                self.logger.debug(f'Reset for {self.address} took {time() - t0:0.1f} sec.')
            else:
                self.logger.debug(f'Reset timeout reached for {self.address}')

    def connect(self) -> MetaWear:
        """
        Attempt to connect to the device. Raise an exception if the maximum number of attempts is exceeded.

        :returns: The connected Mbient device object.
        """
        device = MetaWear(self.address)

        success = False
        self.logger.debug(f'Attempting connection to {self.address}')
        for i in range(self.connect_attempts):
            try:
                if i > 0:  # Do not immediately try to reconnect if it just failed.
                    sleep(3)

                device.connect()
                success = True
                break
            except Exception as e:
                self.logger.debug(f'Failed to connect to {self.address} on attempt {i+1}: {e}')

        if not success:
            raise Exception(f'Unable to connect to {self.address}')

        device.on_disconnect = lambda status: self.on_disconnect(status)
        return device

    def on_disconnect(self, status) -> None:
        self.logger.debug(f'Disconnected {self.address} with status {status}.')
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


def main():
    logger = make_default_logger()
    args = parse_arguments()

    if args.mac:
        devices = {f'CL-{i}': address for i, address in enumerate(args.mac)}
        logger.debug(f'Using {len(devices)} devices specified via command line: {devices}')
    else:
        t0 = time()
        logger.info('Scanning for devices...')
        devices = scan_BLE(timeout_sec=args.scan_timeout, n_devices=args.n_devices)
        logger.info(f'Identified {len(devices)} devices. Scan took {time() - t0:0.1f} sec.')
        if len(devices) == 0:
            logger.error('No devices found!')
            return
        elif len(devices) < args.n_devices:
            logger.warning('Not all devices found!')

    for k, v in devices.items():
        logger.debug(f'Device {k} Address: {v}')

    reset_threads = [
        ResetDeviceThread(
            address=address,
            connect_attempts=args.n_connect_attempts,
            reset_timeout=args.reset_timeout,
        ) for _, address in devices.items()
    ]
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


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger = logging.getLogger('default')
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        raise e
