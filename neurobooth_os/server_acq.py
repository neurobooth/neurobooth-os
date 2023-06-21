import socket
import os
import sys
from time import time, sleep
from collections import OrderedDict
import cv2
import numpy as np
from pylsl import local_clock
import logging

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.netcomm import NewStdout, get_client_messages
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import (
    start_lsl_threads,
    close_streams,
    reconnect_streams,
    connect_mbient,
)
import neurobooth_os.iout.metadator as meta
from neurobooth_os.logging import make_session_logger


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


def Main():
    os.chdir(neurobooth_os.__path__[0])

    sys.stdout = NewStdout("ACQ", target_node="control", terminal_print=True)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Initialize logging to nothing, will get overwritten during session preparation
    logger = logging.getLogger('null')
    logger.addHandler(logging.NullHandler())

    streams = {}
    lowFeed_running = False
    recording = False
    for data, connx in get_client_messages(s1):
        logger.info(f'MESSAGE RECEIVED: {data}')

        if "vis_stream" in data:
            if not lowFeed_running:
                lowFeed = VidRec_Brio(
                    camindex=config.paths["cam_inx_lowfeed"], doPreview=True
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
            subject_id_date = log_task["subject_id-date"]

            conn = meta.get_conn(database=database_name)
            ses_folder = f"{config.paths['data_out']}{subject_id_date}"
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            logger = make_session_logger(ses_folder, 'ACQ')
            logger.info('LOGGER CREATED')

            task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)
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

        elif "record_start" in data:
            # "record_start::filename::task_id" FILENAME = {subj_id}_{obs_id}
            print("Starting recording")
            t0 = time()
            fname, task = data.split("::")[1:]
            fname = f"{config.paths['data_out']}{subject_id_date}/{fname}"

            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                    if task_devs_kw[task].get(k):
                        try:
                            streams[k].start(fname)
                        except:
                            continue

            for k in streams.keys():
                if "Mbient" in k:
                    try:
                        if not streams[k].device.is_connected:
                            streams[k].try_reconnect()
                    except Exception as e:
                        print(e)
                        pass

            elapsed_time = time() - t0
            print(f"Device start took {elapsed_time:.2f}")
            logger.info(f'Device start took {elapsed_time:.2f}')
            msg = "ACQ_devices_ready"
            connx.send(msg.encode("ascii"))
            recording = True

        elif "record_stop" in data:
            t0 = time()
            for k in streams.keys():  # Call stop on streams with that method
                if k.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                    if task_devs_kw[task].get(k):
                        streams[k].stop()

            for k in streams.keys():  # Ensure the streams are stopped
                if k.split("_")[0] in ["FLIR", "Intel", "IPhone"]:
                    if task_devs_kw[task].get(k):
                        streams[k].ensure_stopped(10)

            elapsed_time = time() - t0
            print(f"Device stop took {elapsed_time:.2f}")
            logger.info(f'Device stop took {elapsed_time:.2f}')
            msg = "ACQ_devices_stoped"
            connx.send(msg.encode("ascii"))
            recording = False

        elif data in ["close", "shutdown"]:
            if "shutdown" in data:
                sys.stdout = sys.stdout.terminal
                s1.close()

            # TODO: It would be nice to generically register logging handlers at each stage of a stream's lifecycle.
            for k in streams.keys():  # Log the list of files present on the iPhone
                if k.split("_")[0] == "IPhone":
                    iphone_files = streams[k].dumpall_getfilelist()
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


Main()
