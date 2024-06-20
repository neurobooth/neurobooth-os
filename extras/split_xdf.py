"""
Command line script to (re)split an XDF file into sensor-specific HDF5 files.
This script is a wrapper that calls the relevant function in Neurobooth-OS, with database logging disabled.
"""

import os
import re
import argparse
from typing import Optional, List

import neurobooth_os.config as cfg
from neurobooth_os.iout.split_xdf import split_sens_files
from neurobooth_os.iout.metadator import get_conn


XDF_NAME_PATTERN = re.compile(r'\d+_\d\d\d\d-\d\d-\d\d_\d\dh-\d\dm-\d\ds_(.*)_R001\.xdf', flags=re.IGNORECASE)


class TaskIDException(Exception):
    pass


def main() -> None:
    args = parse_arguments()
    print(f'Splitting {args.xdf}')
    hdf5_files = split_xdf(args.xdf, args.config, args.task_id)
    for f in hdf5_files:
        print(f'   - Created: {f}')


def split_xdf(xdf_path: str, config_file: Optional[str] = None, task_id: Optional[str] = None) -> List[str]:
    cfg.load_config(config_file, validate_paths=False)
    conn = get_conn(database=cfg.neurobooth_config["database"]["dbname"])

    folder, filename = os.path.split(xdf_path)
    if task_id is None:
        task_id = extract_task_id(filename)

    return split_sens_files(
        os.path.join(folder, filename),
        task_id=task_id,
        conn=conn,
    )


def extract_task_id(filename: str) -> str:
    match = re.match(XDF_NAME_PATTERN, filename)
    if match is None:
        raise TaskIDException(f'Unable to determine task ID from file name: {filename}')
    return match.group(1)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Split an XDF file into sensor-specific HDF5 files.')
    parser.add_argument(
        '--xdf',
        required=True,
        type=str,
        help='The XDF file to split.'
    )
    parser.add_argument(
        '--config',
        default=None,
        type=str,
        help='Path to the Neurobooth-OS config file (specifying database credentials, among other things).'
    )
    parser.add_argument(
        '--task-id',
        default=None,
        type=str,
        help='The task ID of the file being split. (Attempt to extract from file name if not specified.)'
    )
    args = parser.parse_args()

    def validate_file(f: str, arg_name: str) -> str:
        f = os.path.abspath(f)
        if not os.path.exists(f) or not os.path.isfile(f):
            parser.error(f'Invalid path supplied for {arg_name}: {f}')
        return f

    args.xdf = validate_file(args.xdf, '--xdf')
    if args.config is not None:
        args.config = validate_file(args.config, '--config')

    return args


if __name__ == '__main__':
    main()
