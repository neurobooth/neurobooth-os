import base64
import os
import sys
from time import time, sleep
from typing import Dict, List, Optional

from pylsl import local_clock
import logging

import neurobooth_os

from neurobooth_os import config
from neurobooth_os.iout.stim_param_reader import TaskArgs, DeviceArgs
from neurobooth_os.log_manager import make_db_logger, log_message_received
from neurobooth_os.iout.lsl_streamer import DeviceManager
import neurobooth_os.iout.metadator as meta
from neurobooth_os.log_manager import SystemResourceLogger
from neurobooth_os.msg.messages import Message, MsgBody, PrepareRequest, RecordingStoppedMsg, StartRecording, \
    RecordingStartedMsg, MbientResetResults, Request, SessionPrepared, FramePreviewReply, \
    ServerStarted, ErrorMessage


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


def main():
    config.load_config_by_service_name("ACQ")  # Load Neurobooth-OS configuration
    logger = make_db_logger()  # Initialize default logger
    try:
        logger.debug("Starting ACQ")
        os.chdir(neurobooth_os.__path__[0])
        run_acq(logger)
        logger.debug("Stopping ACQ")

    except Exception as argument:
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                        exc_info=sys.exc_info())
        raise argument

    finally:
        logging.shutdown()


def run_acq(logger):

    db_conn = meta.get_database_connection()

    device_manager = None
    recording = False
    system_resource_logger = None
    task_args: Dict[str, TaskArgs] = {}
    shutdown_flag = False
    init_servers = Request(source="ACQ", destination="CTR", body=ServerStarted())
    meta.post_message(init_servers, db_conn)
    task: Optional[str] = None  # id of currently executing task, if any
    while not shutdown_flag:

        try:
            message: Message = meta.read_next_message("ACQ", conn=db_conn)
            if message is None:
                sleep(.25)
                continue
            msg_body: Optional[MsgBody] = None
            log_message_received(message, logger)
            current_msg_type : str = message.msg_type
            if "PrepareRequest" == current_msg_type:
                msg_body: PrepareRequest = message.body

                subject_id: str = msg_body.subject_id
                session_name: str = msg_body.session_name()
                collection_id: str = msg_body.collection_id

                ses_folder = os.path.join(config.neurobooth_config.acquisition.local_data_dir, session_name)
                if not os.path.exists(ses_folder):
                    os.mkdir(ses_folder)

                logger = make_db_logger(subject_id, session_name)
                logger.info('LOGGER CREATED')

                if system_resource_logger is None:
                    system_resource_logger = SystemResourceLogger(machine_name='ACQ')
                    system_resource_logger.start()

                task_args = meta.build_tasks_for_collection(collection_id)

                device_manager = DeviceManager(node_name='acquisition')
                if device_manager.streams:
                    device_manager.reconnect_streams()
                else:
                    device_manager.create_streams(task_params=task_args)
                updator = Request(source="ACQ", destination="CTR", body=SessionPrepared())
                meta.post_message(updator, db_conn)

            elif "FramePreviewRequest" == current_msg_type and not recording:
                iphone_frame_preview(db_conn, device_manager, logger)

            # TODO: Both reset_mbients and frame_preview should be reworked as dynamic hooks that register a callback
            elif "ResetMbients" == current_msg_type:

                reset_results = device_manager.mbient_reset()

                reply_body = MbientResetResults(results=reset_results)
                reply = Request(
                    source="ACQ",
                    destination="STM",
                    body=reply_body
                )
                meta.post_message(reply, db_conn)
                logger.debug('Reset results sent')

            elif "StartRecording" == current_msg_type:
                msg_body: StartRecording = message.body

                task = msg_body.task_id
                fname = msg_body.fname
                session_name = msg_body.session_name
                fname = os.path.join(config.neurobooth_config.acquisition.local_data_dir, session_name, fname)

                elapsed_time = start_recording(device_manager, fname, task_args[task].device_args)
                logger.info(f'Device start took {elapsed_time:.2f} for {task}')
                reply = RecordingStartedMsg()
                meta.post_message(reply, db_conn)
                recording = True

            elif "StopRecording" == current_msg_type:
                elapsed_time = stop_recording(device_manager, task_args[task].device_args)
                logger.info(f'Device stop took {elapsed_time:.2f} for {task}')
                reply = RecordingStoppedMsg()
                meta.post_message(reply, db_conn)
                recording = False

            elif "TerminateServerRequest" == current_msg_type:
                if recording:
                    elapsed_time = stop_recording(device_manager, task_args[task].device_args)
                    logger.info(f'Device stop took {elapsed_time:.2f}')

                if device_manager is not None:
                    device_manager.close_streams()

                if system_resource_logger is not None:
                    system_resource_logger.stop()
                logging.shutdown()
                shutdown_flag = True
            else:
                logger.error(f'Unexpected message received: {message.model_dump_json()}')
        except Exception as argument:
            with meta.get_database_connection() as db_conn:
                err_msg = ErrorMessage(status="CRITICAL", text=repr(argument))
                req = Request(body=err_msg, source="ACQ", destination="CTR")
                meta.post_message(req, db_conn)
            raise argument


def iphone_frame_preview(db_conn, device_manager, logger):
    frame = device_manager.iphone_frame_preview()
    if frame is None:
        body = FramePreviewReply(image=None, image_available=False)
    else:
        b64_frame = base64.b64encode(frame).decode('utf-8')
        body = FramePreviewReply(image=b64_frame, image_available=True)
    reply = Request(source="ACQ", destination="CTR", body=body)
    meta.post_message(reply, db_conn)
    if body.image_available:
        logger.debug('Frame preview sent')
    else:
        logger.debug('Frame preview unavailable')


def start_recording(device_manager: DeviceManager, fname: str, task_devices: List[DeviceArgs]) -> float:
    t0 = time()
    device_manager.start_cameras(fname, task_devices)
    device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected
    elapsed_time = time() - t0
    return elapsed_time


def stop_recording(device_manager: DeviceManager, task_devices: List[DeviceArgs]) -> float:
    t0 = time()
    device_manager.stop_cameras(task_devices)
    elapsed_time = time() - t0
    return elapsed_time


if __name__ == '__main__':
    main()
