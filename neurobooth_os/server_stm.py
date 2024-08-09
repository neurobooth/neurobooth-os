import logging
import sys
import os
from collections import OrderedDict  # This import is required for eval
from time import time, sleep
from datetime import datetime
import copy

from concurrent.futures import ThreadPoolExecutor, wait

from typing import Dict, Optional, Callable, List
from psychopy import prefs

from neurobooth_os.iout.stim_param_reader import TaskArgs
from neurobooth_os.msg.messages import Message, CreateTaskRequest, StatusMessage, PerformTaskRequest, \
    TaskInitialization, Request, TaskCompletion, StartRecordingMsg, MsgBody, StartRecording
from neurobooth_os.stm_session import StmSession
from neurobooth_os.tasks import Task
from neurobooth_os.util.task_log_entry import TaskLogEntry

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

import neurobooth_os
from neurobooth_os import config

from neurobooth_os.iout import metadator as meta

from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.log_manager import make_db_logger


def main():
    config.load_config_by_service_name("STM")  # Load Neurobooth-OS configuration
    logger = make_db_logger()  # Initialize logging to default
    try:
        logger.debug("Starting STM")
        os.chdir(neurobooth_os.__path__[0])
        run_stm(logger)
        logger.debug("Stopping STM")
    except Exception as argument:
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                        exc_info=sys.exc_info())
        raise argument
    finally:
        logging.shutdown()


def run_stm(logger):

    presented: bool = False
    paused: bool = False
    session: Optional[StmSession] = None
    task_log_entry: Optional[TaskLogEntry] = None
    db_conn = meta.get_database_connection(database=config.neurobooth_config.database.dbname)

    shutdown_flag = False
    while not shutdown_flag:
        message: Message = meta.read_next_message("STM", conn=db_conn)
        if message is None:
            sleep(1)
            continue
        msg_body: Optional[MsgBody] = None
        logger.info(f'MESSAGE RECEIVED: {message.model_dump_json()}')
        logger.info(f'MESSAGE RECEIVED: {message.body.model_dump_json()}')
        current_msg_type: str = message.msg_type
        if "PrepareRequest" == current_msg_type:
            session, task_log_entry = prepare_session(data, logger)

        elif "CreateTaskRequest" == current_msg_type:  # -> "present:TASKNAME:subj_id:session_id"
            # task_name can be list of tk1-task2-task3
            msg_body = message.body
            session.logger.info(f"Creating Task {msg_body.task_id}")
            tasks, subj_id, session_id = data.split(":")[1:]
            task_log_entry.log_session_id = session_id

            # Preload tasks media
            t0 = time()

            # split into a list of task_id strings
            tasks = tasks.split("-")
            task_list: List[TaskArgs] = []
            for task_id in tasks:
                if task_id in session.tasks():
                    task_args: TaskArgs = _get_task_args(session, task_id)
                    task_list.append(task_args)
                    logger.info(task_args)
                    tsk_fun_obj: Callable = copy.copy(
                        task_args.task_constructor_callable)  # callable for Task constructor
                    logger.info(tsk_fun_obj)
                    this_task_kwargs = create_task_kwargs(session, task_args)
                    logger.info(this_task_kwargs)
                    task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
                    logger.info(task_args.task_instance)
            device_log_entry_dict = meta.log_devices(session.db_conn, task_list)
            session.logger.info(f'Task media took {time() - t0:.2f}')
            session.win = welcome_screen(win=session.win)

            task_calib = [t for t in tasks if "calibration_task" in t]
            # Show calibration instruction video only the first time
            calib_instructions = True

        elif "PerformTaskRequest" == current_msg_type:  #:
            msg_body = message.body
            task_id: str = msg_body.task_id

            session.logger.info(f'TASK: {task_id}')
            tsk_start_time = datetime.now().strftime("%Hh-%Mm-%Ss")

            if task_id not in session.tasks():
                session.logger.warning(f'Task {task_id} not implemented')
            else:
                t00 = time()
                # get task and params
                task_args: TaskArgs = _get_task_args(session, task_id)
                task: Task = task_args.task_instance
                this_task_kwargs = create_task_kwargs(session, task_args)
                task_id = task_args.task_id

                # Do not record if intro instructions"
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
                    init_task_body = TaskInitialization(task_id=task_id,
                                                        log_task_id=log_task_id,
                                                        tsk_start_time=tsk_start_time)
                    meta.post_message(Request(source='STM', destination='CTR', body=init_task_body), conn=db_conn)
                    session.logger.info(f'Initiating task:{task_id}:{task_id}:{log_task_id}:{tsk_start_time}')

                    # TODO: Move this logic to separate function
                    ctr_msg_found: bool = False
                    attempt = 0
                    while not ctr_msg_found and attempt < 4:
                        ctr_msg_found = meta.read_next_lsl_message("STM", db_conn) is not None
                        sleep(1)
                        attempt = attempt + 1
                    elapsed_time = time() - t0
                    session.logger.info(f'Waiting for LSL startup took: {elapsed_time:.2f}')

                    with ThreadPoolExecutor(max_workers=1) as executor:
                        start_acq(calib_instructions, executor, session, task_args,
                                  task_id, this_task_kwargs, tsk_start_time)

                    this_task_kwargs.update({"last_task": len(tasks) == 0})
                    this_task_kwargs["task_name"] = task_id
                    this_task_kwargs["subj_id"] += "_" + tsk_start_time

                    elapsed_time = time() - t00
                    session.logger.info(f"Total TASK WAIT start took: {elapsed_time:.2f}")

                    session.logger.debug(f"RUNNING TASK FUNCTION")
                    events = task.run(**this_task_kwargs)
                    session.logger.debug(f"TASK FUNCTION RETURNED")

                    with ThreadPoolExecutor(max_workers=1) as executor:
                        stop_acq(executor, session, task_args)

                    # Signal CTR to stop LSL rec
                    meta.post_message(Request(source='STM', destination='CTR', body=TaskCompletion(task_id=task_id)),
                                      db_conn)
                    print(f"Finished task: {task_id}")
                    session.logger.info(f'FINISHED TASK: {task_id}')

                    log_task(events, session, task_id, task_id, task_log_entry, task)

                    elapsed_time = time() - t00
                    session.logger.info(f"Total TASK WAIT stop took: {elapsed_time:.2f}")

        if "PauseSessionRequest" == current_msg_type:
            paused = True
            data = pause(session)

        # Next message tells what to do now that we paused
        if "ResumeSessionRequest" == current_msg_type:
            paused = False
            continue

        elif "StopSessionRequest" == current_msg_type:
            break
        elif "CalibrationRequest" == current_msg_type:
            if not len(task_calib):
                continue
            tasks.insert(0, task_calib[0])
            calib_instructions = False

        elif "ShutdownRequest" == current_msg_type:
            if session is not None:
                session.shutdown()
            break

        else:
            if paused:
                meta.post_message(StatusMessage())
                print("Received an unexpected message while paused ")
                logger.warn("Received an unexpected message while paused ")
                session.logger.debug('FINISH SCREEN')
                finish_screen(session.win)

            else:
                logger.error(f'Unexpected message received: {data}')

    exit()


def _get_task_args(session: StmSession, task_id: str):
    if session.task_func_dict is None:
        raise RuntimeError("task_func_dict is not set in StmSession")
    return session.task_func_dict[task_id]


def stop_acq(executor, session: StmSession, task_args: TaskArgs):
    """ Stop recording on ACQ in parallel to stopping on STM """
    session.logger.info(f'SENDING record_stop TO ACQ')
    stimulus_id = task_args.stim_args.stimulus_id

    # TODO: Replace with new message
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

    # TODO: Replace with new message
    fname = f"{session.session_name}_{tsk_start_time}_{task_id}"
    meta.post_message(StartRecordingMsg(
        body=StartRecording(
            session_name=session.session_name,
            fname=fname,
            task_id= task_id
        ))
    )

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
    wait([acq_result])  # Wait for ACQ to finish
    acq_result.result()  # Raise any exceptions swallowed by the executor


def pause(session):
    """ Handle session pause """
    pause_screen = utl.create_text_screen(session.win, text="Session Paused")
    utl.present(session.win, pause_screen, waitKeys=False)
    # TODO: Does the pause message pass any data?
    data=''
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
    meta.fill_task_row(task_log_entry, stm_session.db_conn)


def prepare_session(data: str, logger):
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
        db_conn=meta.get_database_connection(database=database_name),
    )
    #  TODO(larry): See about refactoring so we don't need to create a new logger here.
    #   (continued) We already have a db_logger, it just needs session attributes
    stm_session.logger = make_db_logger(subject_id, stm_session.session_name)
    stm_session.logger.info('LOGGER CREATED FOR SESSION')
    print("UPDATOR:-Connect-")
    return stm_session, task_log_entry


def create_task_kwargs(session: StmSession, task_args: TaskArgs) -> Dict:
    """ Returns a dictionary of arguments """
    result: Dict
    if task_args.instr_args is not None:
        result = {**session.as_dict(), **dict(task_args.stim_args), **dict(task_args.instr_args)}
    else:
        result = {**session.as_dict(), **dict(task_args.stim_args)}
    return result


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


if __name__ == '__main__':
    main()
