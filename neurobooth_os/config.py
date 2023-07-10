# -*- coding: utf-8 -*-
"""
    Ensures that the base neurobooth-os config file exists and makes config file available as neurobooth_config
"""
import os.path as op
from os.path import expanduser
import json

from neurobooth_os.logging import make_default_logger

# if files does not exist raise an exception
# TODO: Get a more specific exception class
logger = make_default_logger()

fname = op.join(expanduser("~"), ".neurobooth_os_config")
if not op.exists(fname):
    msg = "Required config file does not exist"
    logger.critical(msg)
    raise Exception(msg)

# TODO: Add another exception here?
with open(fname, "r") as f:
    neurobooth_config = json.load(f)
