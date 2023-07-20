# -*- coding: utf-8 -*-
"""
    Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""

from os import environ, path
import json

from neurobooth_os.util.constants import NODE_NAMES


def validate_folder(value):
    if not path.exists(value):
        raise FileNotFoundError(f"The folder '{value}' does not exist.")
    if not path.isdir(value):
        raise IOError(f"The path '{value}' is not a folder.")


fname = path.join(environ.get("NB_CONFIG"), "neurobooth_os_config.json")

if not path.exists(fname):
    msg = "Required config file does not exist"
    raise IOError(msg)

with open(fname, "r") as f:
    neurobooth_config = json.load(f)

    validate_folder(neurobooth_config["remote_data_dir"])
    validate_folder(neurobooth_config["video_tasks"])
    validate_folder(neurobooth_config["default_log_path"])

    for name in NODE_NAMES:
        source = neurobooth_config[name]["local_data_dir"]
        if not path.exists(source):
            raise FileNotFoundError(f"The local_data_dir '{source}' for server {name} does not exist.")
        if not path.isdir(source):
            raise IOError(f"The local_data_dir '{source}' for server {name} is not a folder.")

