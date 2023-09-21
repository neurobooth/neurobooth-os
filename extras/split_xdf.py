"""
Command line script to (re)split an XDF file into sensor-specific HDF5 files.
This script is a wrapper that calls the relevant function in Neurobooth-OS, with database logging disabled.
"""

import argparse
from neurobooth_os.iout.split_xdf import split_sens_files
from neurobooth_os.iout.metadator import get_conn


def main() -> None:
    pass


if __name__ == '__main__':
    main()
