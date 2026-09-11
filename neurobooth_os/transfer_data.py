"""
    Moves data from local storage to network storage
"""
import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from subprocess import PIPE, Popen, STDOUT, CalledProcessError

from neurobooth_os import config
from neurobooth_os.log_manager import make_db_logger


def log_output(pipe):
    for line in iter(pipe.readline, b''):  # b'\n'-separated lines
        if '*EXTRA' in line.decode("utf-8"):  # robocopy-specific noise
            continue
        logger.info(str(line, "utf-8").strip('\r\n'))


def _move_tree_robocopy(source: str, destination: str) -> None:
    """Move a directory tree with robocopy. Windows only."""
    process = Popen(["robocopy", "/MOVE", source, destination, "/e"], stdout=PIPE, stderr=STDOUT)
    with process.stdout:
        log_output(process.stdout)
    return_code = process.wait()
    # robocopy's exit codes are a bit field: values below 8 are success with
    # varying amounts of copying done, 8 and above are genuine failures.
    if return_code >= 8:
        raise OSError(f"robocopy failed moving '{source}' to '{destination}' (exit {return_code})")
    logger.info(f"Transfer data to remote. Return code: {return_code}")


def _move_tree_shutil(source: str, destination: str) -> None:
    """Move a directory tree with the standard library.

    ``shutil.move`` on a directory would nest source inside destination when
    destination already exists, which is not what robocopy /MOVE does, so this
    walks the tree and moves entries individually. Empty source directories are
    removed as they are emptied, matching /MOVE's behaviour.
    """
    source_root = Path(source)
    destination_root = Path(destination)
    destination_root.mkdir(parents=True, exist_ok=True)

    moved = 0
    for current_dir, _subdirs, filenames in os.walk(source_root, topdown=False):
        current_path = Path(current_dir)
        target_dir = destination_root / current_path.relative_to(source_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename in filenames:
            shutil.move(str(current_path / filename), str(target_dir / filename))
            moved += 1
        if current_path != source_root and not any(current_path.iterdir()):
            current_path.rmdir()
    logger.info(f"Transfer data to remote. Moved {moved} files.")


def move_tree(source: str, destination: str) -> None:
    """Move everything under ``source`` into ``destination``.

    robocopy is a Windows utility, so the booths keep using it -- it is faster
    on large video trees and operators read its output. Elsewhere the standard
    library does the same job with no external binary.
    """
    if sys.platform == "win32":
        _move_tree_robocopy(source, destination)
    else:
        _move_tree_shutil(source, destination)


def main(args: argparse.Namespace):
    destination = config.neurobooth_config.remote_data_dir
    source = config.neurobooth_config.current_server().local_data_dir

    try:
        move_tree(source, destination)

        # Recreate local data folder
        os.makedirs(source, exist_ok=True)
        logger.info(f"Recreated local data directory: '{source}'")

    except (OSError, CalledProcessError) as exception:
        logger.critical('Exception occurred: ' + str(exception))
        logger.critical('Data transfer failed')
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
