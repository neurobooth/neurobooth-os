import copy
import logging
import os
import sys
from datetime import datetime, time
from threading import Thread
from typing import Optional, Dict, List, Callable
from collections import OrderedDict  # This import is required for eval

from fastapi import FastAPI
from psychopy import prefs

import neurobooth_os
import neurobooth_os.iout.metadator as meta
import neurobooth_os.tasks.utils as utl

from neurobooth_os import config
from neurobooth_os.iout.stim_param_reader import TaskArgs
from neurobooth_os.log_manager import make_db_logger
from neurobooth_os.netcomm import socket_message, NewStdout, get_data_with_timeout
from neurobooth_os.stm_session import StmSession
from neurobooth_os.tasks import Task
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
from neurobooth_os.util.task_log_entry import TaskLogEntry
from concurrent.futures import ThreadPoolExecutor, wait


api_title = "Neurobooth STM API"
api_description = """
The Neurobooth STM API controls the operation of the stimulus function in Neurobooth. Using this API, 
the developer can start and stop an STM process, as well as control at the task level the delivery of task stimuli
that measures the neurological function of test subjects. These tasks are ultimately delivered using Pyschopy.
"""

tags_metadata = [
    {
        "name": "setup",
        "description": "Operations that prepare the STM process for handling Psychopy tasks.",
    },
    {
        "name": "session operation",
        "description": "Operations that handle the delivery of task stimuli to subjects, "
                       "and coordination between STM task-delivery and other processes.",
    },
    {
        "name": "server operations",
        "description": "Operations to manage the starting and stopping of the server process.",
    },
    {
        "name": "testing",
        "description": "Operations for testing the functioning of the STM process.",
    },
]

app = FastAPI(
    title=api_title,
    description=api_description,
    summary="API for messaging to control the operation of the Neurobooth STM (stimulus) function.",
    version="0.0.1",
    tags_metadata = tags_metadata,
)

# TODO: move to config file?
prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

config.load_config(validate_paths=False)
logger = make_db_logger()  # Initialize logging to default
logger.debug("Am I working?")
port: int = config.neurobooth_config.presentation.port
host: str = ''  # Listen on all network interfaces

presented: bool = False
session: Optional[StmSession] = None
task_log_entry: Optional[TaskLogEntry] = None

subj_id: Optional[str] = None
device_log_entry_dict: Optional[Dict] = None
calib_instructions = False


@app.get("/prepare/{collection_id}", tags=["setup"])
async def prepare_req(collection_id: str, database_name: str, subject_id: int, session_id: str):
    global session
    global task_log_entry
    global subj_id

    subj_id = subject_id
    logger.info(f'MESSAGE RECEIVED: Prepare for session {session_id} for {subject_id}')
    session, task_log_entry = prepare_session(collection_id, database_name, subject_id, session_id, logger)
    # initialize_presentation(session_id)
    return {"message": "Ready to handle tasks"}


@app.get("/end_session", tags=["session operation"])
async def end_session_req():
    logger.info("MESSAGE RECEIVED: End session")
    session.logger.debug('FINISH SCREEN')
    finish_screen(session.win)
    return {"message": "Session is finished"}


@app.get("/present/{task_id}", tags=['session operation'])
async def present_req(task_id: str):

    await present(task_id)

    return {"message": f"Presenting task '{task_id}'"}


async def present(task_id):
    global calib_instructions
    session.logger.info(f'MESSAGE RECEIVED: Present {task_id}')
    tsk_start_time = datetime.now().strftime("%Hh-%Mm-%Ss")
    if task_id not in session.tasks():
        session.logger.warning(f'Task {task_id} not implemented')
    else:
        t00 = time()
        # get task and params
        task_args: TaskArgs = _get_task_args(session, task_id)
        task: Task = task_args.task_instance

        # task_list.append(task_args)
        logger.info(task_args)
        tsk_fun_obj: Callable = copy.copy(task_args.task_constructor_callable)  # callable for Task constructor
        this_task_kwargs = create_task_kwargs(session, task_args)
        task_args.task_instance = tsk_fun_obj(**this_task_kwargs)

        # Do not record if intro instructions
        if "intro_" in task_id or "pause_" in task_id:
            session.logger.debug(f"RUNNING PAUSE/INTRO (No Recording)")
            task.run(**this_task_kwargs)
        else:
            log_task_id = meta.make_new_task_row(session.db_conn, subj_id)
            meta.log_task_params(
                session.db_conn,
                log_task_id,
                device_log_entry_dict,
                session.task_func_dict[task_id]
            )
            task_log_entry.date_times = (
                    "{" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ","
            )
            task_log_entry.log_task_id = log_task_id

            # Signal CTR to start LSL rec and wait for start confirmation
            session.logger.info(f'STARTING TASK: {task_id}')
            t0 = time()

            # TODO: Move print to GUI
            print(f"Initiating task:{task_id}:{task_id}:{log_task_id}:{tsk_start_time}")
            session.logger.info(f'Initiating task:{task_id}:{task_id}:{log_task_id}:{tsk_start_time}')

            # TODO: Can this be handled by splitting message and issuing request from GUI side?
            ctr_msg: Optional[str] = None
            while ctr_msg != "lsl_recording":
                ctr_msg = get_data_with_timeout(session.socket, 4)
            elapsed_time = time() - t0
            session.logger.info(f'Waiting for CTR took: {elapsed_time:.2f}')

            with ThreadPoolExecutor(max_workers=1) as executor:
                start_acq(calib_instructions, executor, session, task_args,
                          task_id, this_task_kwargs, tsk_start_time)

            this_task_kwargs["task_name"] = task_id
            this_task_kwargs["subj_id"] += "_" + tsk_start_time

            elapsed_time = time() - t00
            session.logger.info(f"Total TASK WAIT start took: {elapsed_time:.2f}")

            session.logger.debug(f"RUNNING TASK FUNCTION")
            events = task.run(**this_task_kwargs)
            session.logger.debug(f"TASK FUNCTION RETURNED")

            with ThreadPoolExecutor(max_workers=1) as executor:
                stop_acq(executor, session, task_args)

            # Signal CTR to start LSL rec and wait for start confirmation
            print(f"Finished task: {task_id}")
            session.logger.info(f'FINISHED TASK: {task_id}')

            log_task(events, session, task_id, task_id, task_log_entry, task)

            elapsed_time = time() - t00
            session.logger.info(f"Total TASK WAIT stop took: {elapsed_time:.2f}")

            # Check if pause requested, unpause or stop

            # TODO: Move all pause logic to GUI
            # if data == "pause tasks":
            #     data = pause(session)
            #
            #     # Next message tells what to do now that we paused
            #     if data == "continue tasks":
            #         continue
            #     elif data == "stop tasks":
            #         break
            #     elif data == "calibrate":
            #         if not len(task_calib):
            #             continue
            #         tasks.insert(0, task_calib[0])
            #         calib_instructions = False
            #     else:
            #         print("Received an unexpected message while paused")
            #         logger.warn("Received an unexpected message while paused")


@app.get("/shut_down", tags=['server operations'])
async def shut_down_server():
    logger.info('MESSAGE RECEIVED: Shut down')

    if session is not None:
        session.shutdown()

    Thread(target=server_exit).start()
    return {"message": "Shutting down STM"}


@app.get("/time_test", tags=['testing'])
async def test_response_time():
    """No-op for calculating round-trip time"""
    logger.info(f'MESSAGE RECEIVED: time_test')
    return {}


@app.get("/pause", tags=['session operation'])
async def pause_req(data):
    logger.info(f'MESSAGE RECEIVED: pause ')
    # pause(session, data)
    return {"message": "paused"}


def server_exit():
    """Wait 10 seconds, then exit this process"""
    time.sleep(10)
    exit()


def prepare_session(collection_id: str, database_name: str, subject_id, session_id, logger):
    logger.info("Preparing STM for operation.")
    logger.info(f"Database name is {database_name}.")
    # task_log_entry = extract_task_log_entry(collection_id, None, database_name)
    # subject_id: str = task_log_entry.subject_id
    stm_session = StmSession(
        logger=logger,
        # session_name=task_log_entry.subject_id_date,
        session_name=session_id,
        collection_id=collection_id,
        db_conn=meta.get_database_connection(database=database_name),
    )
    #  TODO(larry): See about refactoring so we don't need to create a new logger here.
    #   (continued) We already have a db_logger, it just needs session attributes
    stm_session.logger = make_db_logger(subject_id, stm_session.session_name)
    stm_session.logger.info('LOGGER CREATED FOR SESSION')
    print("UPDATOR:-Connect-")

    ##############################################################
    # Do the initial present work

    return stm_session, task_log_entry


def initialize_presentation(session_id: str):

    global device_log_entry_dict

    session.logger.info("Beginning Presentation")
    task_log_entry.log_session_id = session_id

    # TODO: Move to device_log_entry_dict creation to CTR?
    # tasks = tasks.split("-")
    # task_list: List[TaskArgs] = []
    # for task_id in tasks:
    #     if task_id in session.tasks():
    #         task_args: TaskArgs = _get_task_args(session, task_id)
    #         task_list.append(task_args)
    #         logger.info(task_args)
    #         tsk_fun_obj: Callable = copy.copy(
    #             task_args.task_constructor_callable)  # callable for Task constructor
    #         this_task_kwargs = create_task_kwargs(session, task_args)
    #         task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
    # device_log_entry_dict = meta.log_devices(session.db_conn, task_list)
    session.win = welcome_screen(win=session.win)
    reset_stdout()

    # TODO: Handle elsewhere
    # task_calib = [t for t in tasks if "calibration_task" in t]
    # # Show calibration instruction video only the first time
    # calib_instructions = True

#
# # TODO: Move this to GUI
# def extract_task_log_entry(collection_id: str, database_name: str):
#     """
#     Extracts and returns an object containing info encoded in the data argument,
#     which is a message from the GUI.
#     The other arguments are used simply to trim the rest of the message
#
#     Parameters
#     ----------
#     collection_id
#     data
#     database_name
#
#     Returns
#     -------
#         TaskLogEntry
#     """
#     # remove the first part of the msg
#     log_entry = eval(
#         data.replace(f"prepare:{collection_id}:{database_name}:", "")
#     )
#
#     # type conversion
#     if log_entry["log_session_id"]:
#         log_entry["log_session_id"] = int(log_entry["log_session_id"])
#     else:
#         log_entry["log_session_id"] = None
#
#     # change name to be usable as an attribute name
#     if log_entry["subject_id-date"]:
#         log_entry["subject_id_date"] = log_entry["subject_id-date"]
#         del log_entry["subject_id-date"]
#
#     return TaskLogEntry(**log_entry)


def reset_stdout():
    """When win is created, stdout pipe is reset to message the control node"""
    if not hasattr(sys.stdout, "terminal"):
        sys.stdout = NewStdout(
            "STM", target_node="control", terminal_print=True
        )


def main():
    global logger

    config.load_config()  # Load Neurobooth-OS configuration
    try:
        logger.debug("Starting STM")
        os.chdir(neurobooth_os.__path__[0])
        sys.stdout = NewStdout("STM", target_node="control", terminal_print=True)
        logger.debug("Stopping STM")
    except Exception as argument:
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                        exc_info=sys.exc_info())
        raise argument
    finally:
        logging.shutdown()


def stop_acq(executor, session: StmSession, task_args: TaskArgs):
    """ Stop recording on ACQ in parallel to stopping on STM """
    session.logger.info(f'SENDING record_stop TO ACQ')
    stimulus_id = task_args.stim_args.stimulus_id
    acq_result = executor.submit(socket_message, "record_stop", "acquisition", wait_data=15)
    # Stop eyetracker
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        if "calibration_task" not in stimulus_id:
            session.eye_tracker.stop()
    wait([acq_result])  # Wait for ACQ to finish
    acq_result.result()  # Raise any exceptions swallowed by the executor


def start_acq(calib_instructions, executor, session: StmSession, task_args: TaskArgs, task_id: str, this_task_kwargs,
              tsk_start_time):
    """
    Start recording on ACQ in parallel to starting on STM

    Parameters
    ----------
    calib_instructions
    executor
    session
    task_args
    task_id
    this_task_kwargs
    tsk_start_time

    Returns
    -------

    """
    session.logger.info(f'SENDING record_start TO ACQ')
    stimulus_id = task_args.stim_args.stimulus_id
    acq_result = executor.submit(
        socket_message,
        f"record_start::{session.session_name}_{tsk_start_time}_{task_id}::{task_id}",
        "acquisition",
        wait_data=10,
    )
    # Start eyetracker if device in task
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        fname = f"{session.path}/{session.session_name}_{tsk_start_time}_{task_id}.edf"
        if "calibration_task" in stimulus_id:  # if not calibration record with start method
            this_task_kwargs.update({"fname": fname, "instructions": calib_instructions})
        else:
            task_args.task_instance.render_image() # Render image on HostPC/Tablet screen
            session.eye_tracker.start(fname)
    session.device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected
    os.wait([acq_result])  # Wait for ACQ to finish
    acq_result.result()  # Raise any exceptions swallowed by the executor


def log_task(events: List,
             stm_session: StmSession,
             task_id: str,
             stimulus_id: str,
             task_log_entry: TaskLogEntry,
             task: Task):
    """
    Parameters
    ----------
    events : List
    stm_session : StmSession
    task_id : str
    stimulus_id : str
    task_log_entry : TaskLogEntry
    task : Task

    Returns
    -------
    None

    -------
    Update log entry in database
    """

    task_log_entry.date_times += (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "}"
    )
    task_log_entry.task_id = task_id
    task_log_entry.event_array = (
        str(events).replace("'", '"')
        if events is not None
        else "event:datestamp"
    )
    task_log_entry.task_notes_file = f"{stm_session.session_name}-{stimulus_id}-notes.txt"
    if task.task_files is not None:
        task_log_entry.task_output_files = task.task_files
    meta.fill_task_row(task_log_entry, stm_session.db_conn)


def create_task_kwargs(session: StmSession, task_args: TaskArgs) -> Dict:
    """ Returns a dictionary of arguments """
    result: Dict
    if task_args.instr_args is not None:
        result = {**session.as_dict(), **dict(task_args.stim_args), **dict(task_args.instr_args)}
    else:
        result = {**session.as_dict(), **dict(task_args.stim_args)}
    return result


def _get_task_args(session: StmSession, task_id: str):
    if session.task_func_dict is None:
        raise RuntimeError("task_func_dict is not set in StmSession")
    return session.task_func_dict[task_id]


def pause(session, data):
    """ Handle session pause """
    pause_screen = utl.create_text_screen(session.win, text="Session Paused")
    utl.present(session.win, pause_screen, waitKeys=False)
    session.logger.info(f'PAUSE MESSAGE RECEIVED: {data}')
    return data


if __name__ == '__main__':
    main()
