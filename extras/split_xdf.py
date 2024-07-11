"""
This file splits an XDF file into constituent HDF5 files. It is meant to be called on the cluster without a full
installation of Neurobooth-OS.
"""

import os
import re
import argparse
from typing import Optional, Dict, Any

import neurobooth_os.iout.split_xdf as xdf


class SplitException(Exception):
    """For generic errors that occur when splitting an XDF file."""
    pass


XDF_NAME_PATTERN = re.compile(r'\d+_\d\d\d\d-\d\d-\d\d_\d\dh-\d\dm-\d\ds_(.*)_R001\.xdf', flags=re.IGNORECASE)


def infer_task_id(xdf_path: str) -> str:
    """
    Attempt to infer the task ID from the XDF file name.
    :param xdf_path: The path to the XDF file.
    :return: The inferred task ID. Raises a SplitException if the filename could not be parsed.
    """
    _, filename = os.path.split(xdf_path)
    match = re.match(XDF_NAME_PATTERN, filename)
    if match is None:
        raise SplitException(f'Unable to determine task ID from file name: {filename}')
    return match.group(1)


def split(
        xdf_path: str,
        task_config: str,
        task_id: Optional[str] = None,
) -> None:
    """
    Split a single XDF file into device-specific HDF5 files.
    Intended to be called either via the command line (via parse_arguments()) or by another script (e.g., one that
    finds and iterates over all files to be split).
    :param xdf_path: The path to the XDF file to split.
    :param task_config: The path to task configuration definitions.
    :param task_id: The task ID string (or None to attempt to infer it from the file name).
    """
    if task_id is None:
        task_id = infer_task_id(xdf_path)

    device_ids = None  # TODO: Get device IDs for the task!

    device_data = xdf.parse_xdf(xdf_path, device_ids)
    # TODO: Apply XDF corrections
    xdf.write_device_hdf5(device_data)


def parse_arguments() -> Dict[str, Any]:
    """
    Parse command line arguments.
    :return: Dictionary of keyword arguments to split().
    """
    parser = argparse.ArgumentParser(description='Split an XDF file into device-specific HDF5 files.')
    parser.add_argument(
        '--xdf',
        required=True,
        type=str,
        help='Path to the XDF file to split.'
    )
    parser.add_argument(
        '--task-config',
        default=None,
        type=str,
        help='Path to the Neurobooth-OS task config folder.'
    )
    parser.add_argument(
        '--task-id',
        default=None,
        type=str,
        help='The task ID of the file being split. (Attempt to extract from file name if not specified.)'
    )
    args = parser.parse_args()
    return {
        'xdf_path': os.path.abspath(args.xdf),
        'task_config': os.path.abspath(args.task_config),
        'task_id': args.task_id,
    }


if __name__ == '__main__':
    split(**parse_arguments())
