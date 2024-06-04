import json
import logging
import os
import socket
import sys

from time import time
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

import neurobooth_os
import neurobooth_os.iout.metadator as meta

from neurobooth_os import config
from neurobooth_os.log_manager import make_db_logger, SystemResourceLogger
from neurobooth_os.iout.lsl_streamer import DeviceManager


api_title = "Neurobooth ACQ API"
api_description = """
The Neurobooth ACQ API controls the operation of the data acquisition function in Neurobooth. Using this API, 
the developer can start and stop an ACQ process, as well as control at the task level the acquisition of data 
that measures the neurological function of test subjects.
"""

tags_metadata = [
    {
        "name": "session operation",
        "description": "Operations that manage the session, including delivery of task stimuli to subjects, "
                       "and acquisition of measurement data.",
    },
    {
        "name": "server operations",
        "description": "Operations to manage the operations of servers in a Neurobooth system.",
    },
    {
        "name": "monitoring",
        "description": "Operations enabling Neurobooth users to monitor the state of a session.",
    },
]

config.load_config(validate_paths=False)  # Load Neurobooth-OS configuration
logger = make_db_logger()  # Initialize default logger

logger.debug("Starting ACQ")
os.chdir(neurobooth_os.__path__[0])

system_resource_logger: Optional[SystemResourceLogger] = None
device_manager: Optional[DeviceManager] = None
task_args = {}
task = None
recording = False
session_name: Optional[str] = None
s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)


try:
    logger.debug("Starting ACQ")
    os.chdir(neurobooth_os.__path__[0])

except Exception as argument:
    logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                    exc_info=sys.exc_info())
    raise argument

finally:
    logger.debug("Stopping ACQ")
    logging.shutdown()

app = FastAPI(
    title=api_title,
    description=api_description,
    summary="API for controlling the operation of the Neurobooth ACQ (data acquisition) function.",
    version="0.0.1",
    tags_metadata=tags_metadata,
)

# TODO: Replace with appropriate URLs
origins = [
    "http://127.0.0.1",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:8082",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/prepare/{collection_id}", tags=['session operation'])
async def prepare(collection_id: str, database_name: str, subject_id: str, session_id: str):
    global system_resource_logger, logger, task_args, device_manager, session_name

    logger.info(f'MESSAGE RECEIVED: prepare {session_id}')
    session_name = session_id

    ses_folder = os.path.join(config.neurobooth_config.acquisition.local_data_dir, session_name)
    if not os.path.exists(ses_folder):
        os.mkdir(ses_folder)

    logger = make_db_logger(subject_id, session_name)
    logger.info('LOGGER CREATED')

    if system_resource_logger is None:
        system_resource_logger = SystemResourceLogger(ses_folder, 'ACQ')
        system_resource_logger.start()

    task_args = meta.build_tasks_for_collection(collection_id)

    device_manager = DeviceManager(node_name='acquisition')
    if device_manager.streams:
        device_manager.reconnect_streams()
    else:
        device_manager.create_streams(collection_id=collection_id, task_params=task_args)
    return "UPDATOR:-Connect-"


@app.get("/record_start/", tags=['session operation'])
async def record_start(fname: str, task_id: str):
    global recording, task
    task = task_id
    logger.debug("Starting recording")
    t0 = time()
    fname = os.path.join(config.neurobooth_config.acquisition.local_data_dir, session_name, fname)
    device_manager.start_cameras(fname, task_args[task].device_args)
    device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected

    elapsed_time = time() - t0
    logger.info(f'Device start took {elapsed_time:.2f}')
    msg = f"ACQ_devices_ready: Device start took {elapsed_time:.2f}"
    recording = True
    return msg


@app.get("/record_stop/", tags=['session operation'])
async def record_stop():
    global recording
    logger.info(f'MESSAGE RECEIVED: record_stop')
    t0 = time()
    device_manager.stop_cameras(task_args[task].device_args)
    elapsed_time = time() - t0
    msg = f"ACQ_devices_stopped. Device stop took  {elapsed_time:.2f}"
    recording = False
    return msg


@app.get("/shut_down", tags=['server operations'])
async def shut_down_server():
    logger.info(f'MESSAGE RECEIVED: shut_down')
    if system_resource_logger is not None:
        system_resource_logger.stop()
    logging.shutdown()

    s1.close()

    if device_manager is not None:
        device_manager.close_streams()


@app.get("/reset_mbients", tags=['server operations'])
async def reset_mbients():
    """Reset mbients"""
    logger.info(f'MESSAGE RECEIVED: reset_mbients')
    reset_results = device_manager.mbient_reset()
    logger.debug('Sending reset results')
    return json.dumps(reset_results)


@app.get("/time_test", tags=['testing'])
async def test_response_time():
    """No-op for calculating round-trip time"""
    logger.info(f'MESSAGE RECEIVED: time_test')
    return {}


@app.get("/frame_preview", tags=['monitoring'])
async def iphone_frame_preview():
    logger.info(f'MESSAGE RECEIVED: frame_preview')
    frame = device_manager.iphone_frame_preview()
    if frame is None:
        logger.debug('Frame preview unavailable. No iPhone was found')
        return "ERROR: no iphone in LSL streams".encode("ascii")
    else:
        frame_prefix = b"::BYTES::" + str(len(frame)).encode("utf-8") + b"::"
        frame = frame_prefix + frame
        logger.debug('Sending Frame preview')
        return frame
