"""
This file splits an XDF file into constituent HDF5 files. It is meant to be called on the cluster without a full
installation of Neurobooth-OS.
"""

import os
import re
import argparse
import datetime
from typing import Dict, NamedTuple

import neurobooth_os.iout.split_xdf as xdf


class SplitException(Exception):
    """For generic errors that occur when splitting an XDF file."""
    pass


XDF_NAME_PATTERN = re.compile(r'(\d+)_(\d\d\d\d-\d\d-\d\d)_\d\dh-\d\dm-\d\ds_(.*)_R001\.xdf', flags=re.IGNORECASE)


class XDFInfo(NamedTuple):
    """Structured representation of an XDF file name."""
    parent_dir: str
    name: str
    subject_id: str
    date: datetime.date
    task_id: str

    @property
    def path(self) -> str:
        return os.path.join(self.parent_dir, self.name)

    @staticmethod
    def parse_xdf_name(xdf_path: str) -> 'XDFInfo':
        """
        Attempt to infer the subject ID, date, and task ID from the XDF file path.
        :param xdf_path: The path to the XDF file.
        :return: A structured representation of the XDF file name.
        """
        parent_dir, filename = os.path.split(xdf_path)
        match = re.match(XDF_NAME_PATTERN, filename)
        if match is None:
            raise SplitException(f'Unable to parse file name: {filename}')

        subject_id, date_str, task_id = match.groups()
        return XDFInfo(
            parent_dir=parent_dir,
            name=filename,
            subject_id=subject_id,
            date=datetime.date.fromisoformat(date_str),
            task_id=task_id,
        )


def split(
        xdf_path: str,
        config_path: str,
) -> None:
    """
    Split a single XDF file into device-specific HDF5 files.
    Intended to be called either via the command line (via parse_arguments()) or by another script (e.g., one that
    finds and iterates over all files to be split).
    :param xdf_path: The path to the XDF file to split.
    :param config_path: The path to a Neurobooth configuration file with a 'database' entry.
    """
    xdf_info = XDFInfo.parse_xdf_name(xdf_path)
    device_ids = None  # TODO: Get device IDs for the task!

    device_data = xdf.parse_xdf(xdf_path, device_ids)
    # TODO: Apply XDF corrections
    xdf.write_device_hdf5(device_data)


def parse_arguments() -> Dict[str, str]:
    """
    Parse command line arguments.
    :return: Dictionary of keyword arguments to split().
    """
    parser = argparse.ArgumentParser(description='Split an XDF file into device-specific HDF5 files.')
    parser.add_argument(
        '--xdf',
        required=True,
        type=str,
        help="Path to the XDF file to split."
    )
    parser.add_argument(
        '--config-path',
        required=True,
        type=str,
        help="Path to a Neurobooth configuration file with a 'database' entry."
    )
    args = parser.parse_args()
    return {
        'xdf_path': os.path.abspath(args.xdf),
        'config_path': os.path.abspath(args.config_path),
    }


if __name__ == '__main__':
    split(**parse_arguments())
