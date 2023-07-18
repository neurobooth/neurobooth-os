# -*- coding: utf-8 -*-
"""
    Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""
import os.path
import os.path as op
from os import environ
import json

from neurobooth_os.util.constants import NODE_NAMES

fname = op.join(environ.get("NB_CONFIG"), "neurobooth_os_config.json")

if not op.exists(fname):
    msg = "Required config file does not exist"
    raise IOError(msg)

with open(fname, "r") as f:
    neurobooth_config = json.load(f)

    destination = neurobooth_config["remote_data_dir"]
    if not os.path.exists(destination):
        raise FileNotFoundError(f"The remote_data_dir ({destination}) does not exist.")
    if not os.path.isdir(destination):
        raise IOError(f"The remote_data_dir ({destination}) is not a folder.")

    for name in NODE_NAMES:
        source = neurobooth_config[name]["local_data_dir"]
        if not os.path.exists(source):
            raise FileNotFoundError(f"The local_data_dir ({source}) for server {name} does not exist.")
        if not os.path.isdir(source):
            raise IOError(f"The local_data_dir ({source}) for server {name} is not a folder.")
