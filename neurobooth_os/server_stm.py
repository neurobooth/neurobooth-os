import logging
import socket
import sys
import os
from collections import OrderedDict  # This import is required for eval
from time import time
from datetime import datetime
import copy

from concurrent.futures import ThreadPoolExecutor, wait

from typing import Dict, Optional, Callable, List
from psychopy import prefs

from neurobooth_os.iout.task_param_reader import TaskArgs
from neurobooth_os.stm_session import StmSession
from neurobooth_os.tasks import Task
from neurobooth_os.util.task_log_entry import TaskLogEntry

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

import neurobooth_os
from neurobooth_os import config

from neurobooth_os.iout import metadator as meta

from neurobooth_os.netcomm import (
    socket_message,
    get_client_messages,
    NewStdout,
    get_data_with_timeout,
)

from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_arguments
from neurobooth_os.log_manager import make_db_logger


def main():
    config.load_config()  # Load Neurobooth-OS configuration
    logger = make_db_logger()  # Initialize logging to default
    try:
        logger.debug("Starting STM")
        os.chdir(neurobooth_os.__path__[0])
        sys.stdout = NewStdout("STM", target_node="control", terminal_print=True)
        run_stm(logger)
        logger.debug("Stopping STM")
    except Exception as Argument:
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(Argument)}",
                        exc_info=sys.exc_info())
        raise Argument
    finally:
        logging.shutdown()


def run_stm(logger):
    # TODO(larry): Add socket to stm_session?
    socket_1: socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    presented: bool = False
    port: int = config.neurobooth_config['presentation']["port"]
    host: str = ''
    session: Optional[StmSession] = None
    task_log_entry: Optional[TaskLogEntry] = None
    task_func_dict: Dict = {}
    for data, socket_conn in get_client_messages(socket_1, port, host):
        logger.info(f'MESSAGE RECEIVED: {data}')

        if "prepare" in data:
            session, task_log_entry = prepare_session(data, socket_1, logger)

        elif "present" in data:  # -> "present:TASKNAME:subj_id:session_id"
            # task_name can be list of tk1-task2-task3
            session.logger.info("Beginning Presentation")
            tasks, subj_id, session_id = data.split(":")[1:]
            task_log_entry.log_session_id = session_id

            if presented:
                task_func_dict: Dict[str, TaskArgs] = get_task_arguments(session.collection_id, session.db_conn)

            # Preload tasks media
            t0 = time()

            # split into a list of stimulus_id strings
            tasks = tasks.split("-")
            for stimulus_id in tasks:
                if stimulus_id in session.tasks():
                    task_args: TaskArgs = session.get_task_aguments(stimulus_id)
                    tsk_fun_obj: Callable = copy.copy(task_args.task_constructor_callable)  # callable for Task constructor
                    this_task_kwargs = create_task_kwargs(session, task_args)
                    task_args.task_instance = tsk_fun_obj(this_task_kwargs)
            session.logger.debug(f'Task media took {time() - t0:.2f}')
            session.win = welcome_screen(win=session.win)
            reset_stdout()

            task_calib = [t for t in tasks if "calibration_task" in t]
            # Show calibration instruction video only the first time
            calib_instructions = True

            while len(tasks):
                stimulus_id: str = tasks.pop(0)

                session.logger.info(f'TASK: {stimulus_id}')
                tsk_start_time = datetime.now().strftime("%Hh-%Mm-%Ss")

                if stimulus_id not in session.tasks():
                    session.logger.warning(f'Task {stimulus_id} not implemented')
                else:
                    t00 = time()
                    # get task and params
                    task_args: TaskArgs = session.get_task_arguments(stimulus_id)
                    task: Task = task_args.task_instance
                    this_task_kwargs = create_task_kwargs(session, task_args)
                    task_id = task_args.task_id

                    # Do not record if intro instructions"
                    if "intro_" in stimulus_id or "pause_" in stimulus_id:
                        session.logger.debug(f"RUNNING PAUSE/INTRO (No Recording)")
                        task.run(**this_task_kwargs)
                    else:
                        log_task_id = meta.make_new_task_row(session.db_conn, subj_id)
                        meta.log_task_params(session.db_conn, stimulus_id, log_task_id, task_func_dict[stimulus_id]["kwargs"])
                        task_log_entry.date_times = (
                                "{" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ","
                        )
                        task_log_entry.log_task_id = log_task_id

                        # Signal CTR to start LSL rec and wait for start confirmation
                        session.logger.info(f'STARTING TASK: {stimulus_id}')
                        t0 = time()
                        print(f"Initiating task:{stimulus_id}:{task_id}:{log_task_id}:{tsk_start_time}")
                        session.logger.info(f'Initiating task:{stimulus_id}:{task_id}:{log_task_id}:{tsk_start_time}')
                        ctr_msg: Optional[str] = None
                        while ctr_msg != "lsl_recording":
                            ctr_msg = get_data_with_timeout(socket_1, 4)
                        elapsed_time = time() - t0
                        session.logger.info(f'Waiting for CTR took: {elapsed_time:.2f}')

                        with ThreadPoolExecutor(max_workers=1) as executor:
                            start_acq(calib_instructions, executor, session, stimulus_id, task_id, this_task_kwargs,
                                      tsk_start_time)

                        this_task_kwargs.update({"last_task": len(tasks) == 0})
                        this_task_kwargs["task_name"] = task_id
                        this_task_kwargs["subj_id"] += "_" + tsk_start_time

                        elapsed_time = time() - t00
                        session.logger.info(f"Total TASK WAIT start took: {elapsed_time:.2f}")

                        session.logger.debug(f"RUNNING TASK FUNCTION")
                        events = task.run(**this_task_kwargs)
                        session.logger.debug(f"TASK FUNCTION RETURNED")

                        with ThreadPoolExecutor(max_workers=1) as executor:
                            stop_acq(executor, session, stimulus_id)

                        # Signal CTR to start LSL rec and wait for start confirmation
                        print(f"Finished task: {stimulus_id}")
                        session.logger.info(f'FINISHED TASK: {stimulus_id}')

                        log_task(events, session, task_id, stimulus_id, task_log_entry, task)

                        elapsed_time = time() - t00
                        session.logger.info(f"Total TASK WAIT stop took: {elapsed_time:.2f}")

                        # Check if pause requested, unpause or stop
                        data = get_data_with_timeout(socket_1, 0.1)
                        if data == "pause tasks":
                            data = pause(session, socket_1)

                            # Next message tells what to do now that we paused
                            if data == "continue tasks":
                                continue
                            elif data == "stop tasks":
                                break
                            elif data == "calibrate":
                                if not len(task_calib):
                                    print("No calibration task")
                                    continue
                                tasks.insert(0, task_calib[0])
                                calib_instructions = False
                                print("Calibration task added")
                            else:
                                print("Received an unexpected message while paused ")

            session.logger.debug('FINISH SCREEN')
            finish_screen(session.win)
            presented = True

        elif "shutdown" in data:
            shutdown(session, socket_1)
            break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            socket_conn.send(msg.encode("ascii"))

        else:
            logger.error(f'Unexpected message received: {data}')

    exit()


def stop_acq(executor, session: StmSession, stimulus_id: str):
    """ Stop recording on ACQ in parallel to stopping on STM """
    session.logger.info(f'SENDING record_stop TO ACQ')
    acq_result = executor.submit(socket_message, "record_stop", "acquisition", wait_data=15)
    # Stop eyetracker
    if session.eye_tracker is not None and any(
            "Eyelink" in d for d in list(session.device_kwargs[stimulus_id])):
        if "calibration_task" not in stimulus_id:
            session.eye_tracker.stop()
    wait([acq_result])  # Wait for ACQ to finish
    acq_result.result()  # Raise any exceptions swallowed by the executor


def start_acq(calib_instructions, executor, session:StmSession, stimulus_id: str, task_id: str, this_task_kwargs,
              tsk_start_time):
    """
    Start recording on ACQ in parallel to starting on STM

    Parameters
    ----------
    calib_instructions
    executor
    session
    stimulus_id
    task_id
    this_task_kwargs
    tsk_start_time

    Returns
    -------

    """
    session.logger.info(f'SENDING record_start TO ACQ')
    acq_result = executor.submit(
        socket_message,
        f"record_start::{session.session_name}_{tsk_start_time}_{task_id}::{stimulus_id}",
        "acquisition",
        wait_data=10,
    )
    # Start eyetracker if device in task
    if session.eye_tracker is not None and any(
            "Eyelink" in d for d in list(session.device_kwargs[stimulus_id])):
        fname = f"{session.path}/{session.session_name}_{tsk_start_time}_{task_id}.edf"
        if "calibration_task" in stimulus_id:  # if not calibration record with start method
            this_task_kwargs.update({"fname": fname, "instructions": calib_instructions})
        else:
            session.eye_tracker.start(fname)
    session.device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected
    wait([acq_result])  # Wait for ACQ to finish
    acq_result.result()  # Raise any exceptions swallowed by the executor


def pause(session, socket_1):
    """ Handle session pause """
    pause_screen = utl.create_text_screen(session.win, text="Session Paused")
    utl.present(session.win, pause_screen, waitKeys=False)
    connx2, _ = socket_1.accept()
    data = connx2.recv(1024)
    data = data.decode("utf-8")
    session.logger.info(f'PAUSE MESSAGE RECEIVED: {data}')
    return data


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
    meta.fill_task_row(task_log_entry.log_task_id, task_log_entry, stm_session.db_conn)


def reset_stdout():
    """When win is created, stdout pipe is reset to message the control node"""
    if not hasattr(sys.stdout, "terminal"):
        sys.stdout = NewStdout(
            "STM", target_node="control", terminal_print=True
        )


def prepare_session(data: str, socket_1: socket, logger):
    logger.info("Preparing STM for operation.")
    collection_id = data.split(":")[1]
    database_name = data.split(":")[2]
    logger.info(f"Database name is {database_name}.")
    task_log_entry = extract_task_log_entry(collection_id, data, database_name)
    subject_id: str = task_log_entry.subject_id
    stm_session = StmSession(
        logger=logger,
        session_name=task_log_entry.subject_id_date,
        collection_id=collection_id,
        db_conn=meta.get_conn(database=database_name),
        socket=socket_1
    )
    # TODO(larry): See about refactoring so we don't need to create a new logger here.
    #   (continued) We already have a db_logger, it just needs session attributes
    stm_session.logger = make_db_logger(subject_id, stm_session.session_name)
    stm_session.logger.info('LOGGER CREATED FOR SESSION')
    print("UPDATOR:-Connect-")
    return stm_session, task_log_entry


def create_task_kwargs(session: StmSession, task_args: TaskArgs) -> Dict:
    """ Returns a dictionary of arguments """
    return {**session.as_dict(), **dict(task_args.stim_args), **dict(task_args.instr_args)}


def extract_task_log_entry(collection_id: str, data: str, database_name: str):
    """
    Extracts and returns an object containing info encoded in the data argument,
    which is a message from the GUI.
    The other arguments are used simply to trim the rest of the message

    Parameters
    ----------
    collection_id
    data
    database_name

    Returns
    -------
        TaskLogEntry
    """
    # remove the first part of the msg
    log_entry = eval(
        data.replace(f"prepare:{collection_id}:{database_name}:", "")
    )

    # type conversion
    if log_entry["log_session_id"]:
        log_entry["log_session_id"] = int(log_entry["log_session_id"])
    else:
        log_entry["log_session_id"] = None

    # change name to be usable as an attribute name
    if log_entry["subject_id-date"]:
        log_entry["subject_id_date"] = log_entry["subject_id-date"]
        del log_entry["subject_id-date"]

    return TaskLogEntry(**log_entry)


def shutdown(stm_session: StmSession, socket_1:socket):
    """Close resources at the end of the session"""
    stm_session.shutdown()
    sys.stdout = sys.__stdout__
    if socket_1 is not None:
        socket_1.close()


if __name__ == '__main__':
    main()
