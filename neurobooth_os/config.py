# -*- coding: utf-8 -*-
"""
    Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""
import os.path as op
from os import environ
import json

fname = op.join(environ.get("NB_CONFIG"), "neurobooth_os_config.json")
if not op.exists(fname):
    msg = "Required config file does not exist"
    raise IOError(msg)

with open(fname, "r") as f:
    neurobooth_config = json.load(f)
