import socket
import os
import sys
from time import time, sleep
from collections import OrderedDict
import cv2
import numpy as np
from pylsl import local_clock
import logging
import json

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.log_manager import make_db_logger
from neurobooth_os.netcomm import NewStdout, get_client_messages
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import DeviceManager
from neurobooth_os.iout.mbient import Mbient
import neurobooth_os.iout.metadator as meta
from neurobooth_os.log_manager import SystemResourceLogger


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


def main():
    config.load_config()  # Load Neurobooth-OS configuration
    logger = make_db_logger()  # Initialize default logger
    try:
        logger.debug("Starting ACQ")
        os.chdir(neurobooth_os.__path__[0])
        sys.stdout = NewStdout("ACQ", target_node="control", terminal_print=True)
        run_acq(logger)
        logger.debug("Stopping ACQ")

    except Exception as e:
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        logger.critical("Stopping ACQ (error-state)")
        raise
    finally:
        logging.shutdown()


def run_acq(logger):
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    lowFeed_running = False
    recording = False
    port = config.neurobooth_config['acquisition']["port"]
    host = ''
    device_manager = None
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
            ses_folder = f"{config.neurobooth_config['acquisition']['local_data_dir']}{session_name}"
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            logger = make_db_logger(subject_id, session_name)
            logger.info('LOGGER CREATED')

            if system_resource_logger is None:
                system_resource_logger = SystemResourceLogger(ses_folder, 'ACQ')
                system_resource_logger.start()

            task_devs_kw = meta.get_device_kwargs_by_task(collection_id, conn)

            device_manager = DeviceManager(node_name='acquisition')
            if device_manager.streams:
                device_manager.reconnect_streams()
            else:
                device_manager.create_streams(collection_id=collection_id, conn=conn)
            print("UPDATOR:-Connect-")

        elif "frame_preview" in data and not recording:
            frame = device_manager.iphone_frame_preview()
            if frame is None:
                print("no iphone")
                connx.send("ERROR: no iphone in LSL streams".encode("ascii"))
                logger.debug('Frame preview unavailable')
            else:
                frame_prefix = b"::BYTES::" + str(len(frame)).encode("utf-8") + b"::"
                frame = frame_prefix + frame
                connx.send(frame)
                logger.debug('Frame preview sent')

        # TODO: Both reset_mbients and frame_preview should be reworked as dynamic hooks that register a callback
        elif "reset_mbients" in data:
            reset_results = device_manager.mbient_reset()
            connx.send(json.dumps(reset_results).encode('utf-8'))
            logger.debug('Reset results sent')

        elif "record_start" in data:
            # "record_start::filename::task_id" FILENAME = {subj_id}_{obs_id}
            print("Starting recording")
            t0 = time()
            fname, task = data.split("::")[1:]
            fname = f"{config.neurobooth_config['acquisition']['local_data_dir']}{session_name}/{fname}"

            device_manager.start_cameras(fname, task_devs_kw[task])
            device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected

            elapsed_time = time() - t0
            print(f"Device start took {elapsed_time:.2f}")
            logger.info(f'Device start took {elapsed_time:.2f}')
            msg = "ACQ_devices_ready"
            connx.send(msg.encode("ascii"))
            recording = True

        elif "record_stop" in data:
            t0 = time()
            device_manager.stop_cameras(task_devs_kw[task])
            elapsed_time = time() - t0
            print(f"Device stop took {elapsed_time:.2f}")
            logger.info(f'Device stop took {elapsed_time:.2f}')
            msg = "ACQ_devices_stopped"
            connx.send(msg.encode("ascii"))
            recording = False

        elif "shutdown" in data:
            if system_resource_logger is not None:
                system_resource_logger.stop()
                system_resource_logger = None
            logging.shutdown()

            sys.stdout = sys.stdout.terminal
            s1.close()

            device_manager.iphone_log_file_list()    # Log the list of files present on the iPhone
            device_manager.close_streams()

            if lowFeed_running:
                lowFeed.close()
                lowFeed_running = False
                print("Closing RTD cam")
            break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            connx.send(msg.encode("ascii"))

        else:
            logger.error(f'Unexpected message received: {data}')


if __name__ == '__main__':
    main()
