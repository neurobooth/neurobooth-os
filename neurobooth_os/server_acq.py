import socket
import os
import sys
from time import time, sleep
from collections import OrderedDict
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor, wait
from pylsl import local_clock
import logging
import json

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.log_manager import make_default_logger, make_db_logger
from neurobooth_os.netcomm import NewStdout, get_client_messages
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import (
    start_lsl_threads,
    close_streams,
    reconnect_streams,
)
from neurobooth_os.iout.mbient import Mbient
import neurobooth_os.iout.metadator as meta
from neurobooth_os.log_manager import SystemResourceLogger

server_config = config.neurobooth_config["acquisition"]

def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


def Main():
    os.chdir(neurobooth_os.__path__[0])
    sys.stdout = NewStdout("ACQ", target_node="control", terminal_print=True)

    # Initialize default logger
    logger = make_default_logger()
    logger.info("Starting ACQ")
    try:
        run_acq(logger)
    except Exception as e:
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        raise


def is_camera(stream_name: str) -> bool:
    """Test to see if a stream is a camera stream based on its name."""
    return stream_name.split("_")[0] in ["FLIR", "Intel", "IPhone"]


def run_acq(logger):
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    streams = {}
    lowFeed_running = False
    recording = False
    port = server_config["port"]
    host = ''
    system_resource_logger = None

    for data, connx in get_client_messages(s1, port, host):
        logger.info(f'MESSAGE RECEIVED: {data}')

        if "vis_stream" in data:
            if not lowFeed_running:
                lowFeed = VidRec_Brio(
                    camindex=config.neurobooth_config["cam_inx_lowfeed"], doPreview=True
                )
                print("LowFeed running")
                lowFeed_running = True
            else:
                print(f"-OUTLETID-:Webcam:{lowFeed.preview_outlet_id}")
                print("Already running low feed video streaming")

        elif "prepare" in data:
            # data = "prepare:collection_id:database:str(log_task_dict)"
            collection_id = data.split(":")[1]
            database_name = data.split(":")[2]
            log_task = eval(
                data.replace(f"prepare:{collection_id}:{database_name}:", "")
            )
            subject_id: str = log_task["subject_id"]
            session_name: str = log_task["subject_id-date"]

            conn = meta.get_conn(database=database_name)

            logger = make_db_logger(subject_id, session_name)
            logger.info('LOGGER CREATED')

            if system_resource_logger is None:
                ses_folder = _make_session_folder(session_name)
                system_resource_logger = SystemResourceLogger(ses_folder, 'ACQ')
                system_resource_logger.start()

            task_devs_kw = meta.get_device_kwargs_by_task(collection_id, conn)
            if len(streams):
                # print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("acquisition", collection_id, conn=conn)

            devs = list(streams.keys())
            logger.info(f'LOADED DEVICES: {str(devs)}')
            print("UPDATOR:-Connect-")

        elif "frame_preview" in data and not recording:
            if not any("IPhone" in s for s in streams):
                print("no iphone")
                connx.send("ERROR: no iphone in LSL streams".encode("ascii"))
                logger.debug('Frame preview unavailable')
                continue

            frame = streams[[i for i in streams if "IPhone" in i][0]].frame_preview()
            frame_prefix = b"::BYTES::" + str(len(frame)).encode("utf-8") + b"::"
            frame = frame_prefix + frame
            connx.send(frame)
            logger.debug('Frame preview sent')

        # TODO: Both reset_mbients and frame_preview should be reworked as dynamic hooks that register a callback
        elif "reset_mbients" in data:
            mbient_streams = {
                stream_name: stream
                for stream_name, stream in streams.items()
                if 'mbient' in stream_name.lower()
            }

            if len(mbient_streams) == 0:
                logger.debug('No mbients to reset.')
                connx.send(json.dumps({}).encode('utf-8'))
                continue

            with ThreadPoolExecutor(max_workers=len(mbient_streams)) as executor:
                # Begin concurrent reset of devices
                reset_results = {
                    stream_name: executor.submit(stream.reset_and_reconnect)
                    for stream_name, stream in mbient_streams.items()
                }

                # Wait for resets to complete, then resolve the futures
                wait(reset_results.values())
                reset_results = {stream_name: result.result() for stream_name, result in reset_results.items()}

            # Reply with the results of the reset
            connx.send(json.dumps(reset_results).encode('utf-8'))
            logger.debug('Reset results sent')

        elif "record_start" in data:
            # "record_start::filename::task_id" FILENAME = {subj_id}_{obs_id}
            print("Starting recording")
            t0 = time()
            fname, task = data.split("::")[1:]
            fname = f"{server_config['local_data_dir']}{session_name}/{fname}"

            # Start cameras
            for stream_name, stream in streams.items():
                if is_camera(stream_name) and stream_name in task_devs_kw[task]:
                    try:
                        stream.start(fname)
                    except Exception as e:
                        logger.exception(e)

            # Attempt to reconnect Mbients if disconnected
            Mbient.task_start_reconnect([
                stream for stream_name, stream in streams.items()
                if 'Mbient' in stream_name
            ])

            elapsed_time = time() - t0
            print(f"Device start took {elapsed_time:.2f}")
            logger.info(f'Device start took {elapsed_time:.2f}')
            msg = "ACQ_devices_ready"
            connx.send(msg.encode("ascii"))
            recording = True

        elif "record_stop" in data:
            t0 = time()

            # Stop cameras
            for stream_name, stream in streams.items():
                if is_camera(stream_name) and stream_name in task_devs_kw[task]:
                    stream.stop()

            # Wait for cameras to actually stop
            for stream_name, stream in streams.items():
                if is_camera(stream_name) and stream_name in task_devs_kw[task]:
                    stream.ensure_stopped(10)

            elapsed_time = time() - t0
            print(f"Device stop took {elapsed_time:.2f}")
            logger.info(f'Device stop took {elapsed_time:.2f}')
            msg = "ACQ_devices_stoped"
            connx.send(msg.encode("ascii"))
            recording = False

        elif data in ["close", "shutdown"]:
            if system_resource_logger is not None:
                system_resource_logger.stop()
                system_resource_logger = None

            if "shutdown" in data:
                sys.stdout = sys.stdout.terminal
                s1.close()

            # TODO: It would be nice to generically register logging handlers at each stage of a stream's lifecycle.
            for k in streams.keys():  # Log the list of files present on the iPhone
                if k.split("_")[0] == "IPhone":
                    iphone_files, _ = streams[k].dumpall_getfilelist()
                    if iphone_files is not None:
                        logger.info(f'iPhone has {len(iphone_files)} waiting for dump: {iphone_files}')
                    else:
                        logger.warning(f'iPhone did not return a list of files to dump.')

            streams = close_streams(streams)

            if "shutdown" in data:
                if lowFeed_running:
                    lowFeed.close()
                    lowFeed_running = False
                    print("Closing RTD cam")
                break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            connx.send(msg.encode("ascii"))

        else:
            print(data)


def _make_session_folder(session_name):
    ses_folder = f"{server_config['local_data_dir']}{session_name}"
    if not os.path.exists(ses_folder):
        os.mkdir(ses_folder)
    return ses_folder


Main()
