"""
    Moves data from local storage to network storage
"""
import subprocess
import argparse

from neurobooth_os import config
from neurobooth_os.netcomm.types import NODE_NAMES
from neurobooth_os.log_manager import make_default_logger


def main(args: argparse.Namespace):

    logger = make_default_logger()

    destination = config.neurobooth_config["remote_data_dir"]

    source = config.neurobooth_config[args.source_node_name]["local_data_dir"]

    # Move data to remote
    result_step_1 = subprocess.run(["robocopy", "/MOVE", source, destination, "/e"])
    print(str(result_step_1))

    # Recreate local data folder
    result_step_2 = subprocess.run(["mkdir", source])
    print(str(result_step_2))


def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        prog='transfer_data',
        description='Transfer data copies data from local folders into remote storage.',
    )

    parser.add_argument(
        'source_node_name',  # positional argument
        choices=NODE_NAMES,
        help=f'You must provide the name of the node to transfer data from, which must be one of {NODE_NAMES}'
    )
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    main(parse_arguments())
