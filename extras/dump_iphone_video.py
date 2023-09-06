import neurobooth_os.iout.iphone as iphone
import neurobooth_os.config as cfg
import re
import os
import os.path as op
import datetime
import logging
from typing import Optional
from neurobooth_os.log_manager import make_default_logger
import argparse
import sys


class TimeoutException(Exception):
    pass


def neurobooth_dump(args: argparse.Namespace) -> None:
    """
    Retrieve a list of files stored in the iPhone and attempt to extract and save them to the session folder specified
    by their file names.

    Parameters
    ----------
    args
        Command line arguments.
    """
    session_root = cfg.neurobooth_config[args.server]["local_data_dir"]
    logger = logging.getLogger('default')
    logger.debug(f'Session Root: {session_root}')

    # Connect to the iPhone
    logger.debug('Connecting to iPhone')
    # It is important that timeout exceptions are enabled to prevent misnamed files!
    phone = iphone.IPhone("dump_iphone", enable_timeout_exceptions=True)
    handshake_success = phone.prepare()
    if not handshake_success:
        logger.error(f'Unable to connect to iPhone [state={phone._state}]!')
        return

    # Get a list of stored files
    file_names, file_hashes = phone.dumpall_getfilelist()
    if file_names is None:
        logger.error(f'Unable to retrieve file list [state={phone._state}]!')
        phone.disconnect()
        return
    logger.debug(f'{len(file_names)} files to transfer: {str(file_names)}')

    # Try to extract and save each file
    for file_name, file_hash in zip(file_names, file_hashes):
        # Parse the session folder out of the file name
        sess_name = re.findall("[0-9]*_[0-9]{4}-[0-9]{2}-[0-9]{2}", file_name)
        if len(sess_name) == 0 or sess_name is None:
            logger.error(f'Invalid session name: file={file_name}; name={sess_name}.')
            continue

        # Make the session folder if it does not exist
        sess_folder = op.join(session_root, sess_name[0])
        if not op.exists(sess_folder):
            logger.debug(f'Creating directory: {sess_folder}')
            os.mkdir(sess_folder)

        try:
            dump_file(
                phone, file_name, op.join(sess_folder, file_name),
                timeout_sec=args.timeout,
                delete_zero_byte=args.delete_zero_byte,
            )
        except iphone.IPhoneTimeout:
            logger.error(
                f'Timeout encountered when retrieving {file_name}. Discontinuing transfer to prevent out-of-order files.'
            )
            break
        except iphone.IPhoneHashMismatch:
            logger.error(f'Hash mismatch detected for {file_name}. Skipping this file.')
            continue

    logger.debug('Disconnecting iPhone')
    phone.disconnect()


def dump_file(
        phone: iphone.IPhone,
        file_name: str,
        file_name_out: str,
        file_hash,
        timeout_sec: Optional[float] = None,
        delete_zero_byte: bool = False,
) -> None:
    """
    Extract a single file from the iPhone, save it in the specified location, and tell the iPhone to delete the file.

    Parameters
    ----------
    phone
        The iPhone object to interface with.
    file_name
        The name of the file on the iPhone (returned by dumpall_getfilelist).
    file_name_out
        The path to save the retrieved file to.
    file_hash
        The hash value of the file, used to check the integrity of the transfer.
    timeout_sec
        If not None, log an error and return if the file transfer exceeds the timeout.
    delete_zero_byte
        If true, delete files from the iPhone if no data is observed.
    """
    logger = logging.getLogger('default')
    if op.exists(file_name_out):  # Do not overwrite a file that already exists
        logger.error(f'Cannot write {file_name_out} as it already exists!')
        return

    # Attempt to retrieve the file from the iPhone
    logger.info(f'Dump {file_name} -> {file_name_out}')
    file_data = phone.dump(file_name, file_hash=file_hash, timeout_sec=timeout_sec)

    zero_byte = len(file_data) == 0
    if zero_byte:
        logger.error(f'{file_name} returned a zero-byte file!')

    try:  # Save the file and delete from the iphone
        with open(file_name_out, "wb") as f:
            f.write(file_data)
        logger.debug(f'Wrote {file_name_out}, {len(file_data) / (1 << 20):0.1f} MiB')

        if not zero_byte or delete_zero_byte:
            phone.dump_success(file_name)  # Delete file from iPhone
            logger.debug(f'Sent @DUMPSUCCESS for {file_name}')
    except Exception as e:
        logger.error(f'Unable to write file {file_name_out}; error={e}')


def parse_arguments() -> argparse.Namespace:
    logger = logging.getLogger('default')
    parser = argparse.ArgumentParser(description='Download and save all files on the iPhone (both .json and .MOV).')
    parser.add_argument(
        '--delete-zero-byte',
        action='store_true',
        help='If set, suspected zero-byte files will be deleted from the iPhone. WARNING: MAY DELETE DATA.'
    )
    parser.add_argument(
        '--timeout',
        default=600,
        type=int,
        help='Specify a timeout (in seconds) for each file retrieval. Default is 10 min. No timeout if <= 0.'
    )
    parser.add_argument(
        '--server',
        default='acquisition',
        type=str,
        help='Specify the server to run on so the proper value of local_data_dir is used. Default is "acquisition".'
    )
    args = parser.parse_args()

    if args.delete_zero_byte:
        logger.warning('USE CAUTION: the --delete-zero-byte argument could potentially lead to data deletion.')

    if args.timeout <= 0:
        logger.warning(f'Infinite timeout specified. The script may hang if an error occurs.')
        args.timeout = None
    elif args.timeout < 15:
        logger.warning(f'Short timeout ({args.timeout} sec) specified. Not all files may be transferred.')

    return args


def main():
    logger = make_default_logger()
    iphone.DISABLE_LSL = True

    args = parse_arguments()
    t0 = datetime.datetime.now()
    logger.info('Running Dump')
    neurobooth_dump(args)
    logger.info(f"Dump Complete; Total Time: {datetime.datetime.now() - t0}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger = logging.getLogger("default")
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        raise
