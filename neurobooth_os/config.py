# -*- coding: utf-8 -*-
"""
Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

from os import environ, path, getenv
from typing import Optional
import json


def get_server_name_from_env() -> Optional[str]:
    """
    This is a hack to get the role of the machine that this code is being executed on. It's based on the
    assumption that the Windows User Profile in use matches one of the servers defined in the config file
    :returns: a server name, or None.
    """
    user = getenv("USERPROFILE")

    if "STM" in user:
        return 'presentation'
    if "ACQ" in user:
        return 'acquisition'
    if "CTR" in user:
        return 'control'

    return None


def validate_folder(value: str) -> None:
    if not path.exists(value):
        raise FileNotFoundError(f"The folder '{value}' does not exist.")
    if not path.isdir(value):
        raise IOError(f"The path '{value}' is not a folder.")


neurobooth_config = None


def load_config(fname: Optional[str] = None, validate_paths: bool = True) -> None:
    """
    Load neurobooth configurations from a file and store them in the `neurobooth_config` module variable.

    :param fname: Path to the configuration file. If None, load the path from the NB_CONFIG environment variable.
    :param validate_paths: Whether to check the validity of key files and directories. Should be True for active
        Nuerobooth sessions. (Toggle is provided for use by secondary scripts.)
    """
    if fname is None:
        fname = path.join(environ.get("NB_CONFIG"), "neurobooth_os_config.json")

    if not path.exists(fname):
        msg = "Required config file does not exist"
        raise IOError(msg)

    with open(fname, "r") as f:
        global neurobooth_config
        neurobooth_config = json.load(f)

        if validate_paths:
            server_name = get_server_name_from_env()
            if server_name is None:
                raise IOError('The server name could not be identified!')

            if server_name == "presentation":
                validate_folder(neurobooth_config["video_tasks"])
            validate_folder(neurobooth_config["remote_data_dir"])
            validate_folder(neurobooth_config["default_log_path"])

            source = neurobooth_config[server_name]["local_data_dir"]
            if not path.exists(source):
                raise FileNotFoundError(f"The local_data_dir '{source}' for server {server_name} does not exist.")
            if not path.isdir(source):
                raise IOError(f"The local_data_dir '{source}' for server {server_name} is not a folder.")
