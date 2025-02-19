"""
    Moves data from local storage to network storage
"""
import logging
import os
from subprocess import PIPE, Popen, STDOUT, CalledProcessError
import argparse

from neurobooth_os import config
from neurobooth_os.log_manager import make_db_logger


def log_output(pipe):
    for line in iter(pipe.readline, b''):  # b'\n'-separated lines
        if '*EXTRA' in line.decode("utf-8"):
            continue
        logger.info(str(line, "utf-8").strip('\r\n'))


def main(args: argparse.Namespace):
    destination = config.neurobooth_config.remote_data_dir
    source = config.neurobooth_config.current_server().local_data_dir

    try:
        # Move data to remote
        process = Popen(["robocopy", "/MOVE", source, destination, "/e"], stdout=PIPE, stderr=STDOUT)
        with process.stdout:
            log_output(process.stdout)
        return_code = process.wait()
        logger.info(f"Transfer data to remote. Return code: {return_code}")

        # Recreate local data folder
        os.makedirs(source, exist_ok=True)
        logger.info(f"Recreated local data directory: '{source}'")

    except (OSError, CalledProcessError) as exception:
        logger.critical('Exception occurred: ' + str(exception))
        logger.critical('Subprocess failed')
        raise exception


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='transfer_data',
        description='Transfer data copies data from local folders into remote storage.',
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    config.load_config()
    logger = make_db_logger()
    try:
        main(parse_arguments())
    except Exception as e:
        logger.critical(e)
    finally:
        logging.shutdown()
