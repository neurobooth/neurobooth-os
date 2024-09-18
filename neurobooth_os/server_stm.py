import logging
import sys
import os
from time import time, sleep
from datetime import datetime
import copy

from typing import Dict, Optional, Callable, List
from psychopy import prefs

from neurobooth_os.iout.stim_param_reader import TaskArgs
from neurobooth_os.msg.messages import Message, CreateTasksRequest, StatusMessage, \
    TaskInitialization, Request, TaskCompletion, StartRecordingMsg, StartRecording, SessionPrepared, \
    PrepareRequest, TasksCreated, Reply, StopRecording, ServerStarted
from neurobooth_os.stm_session import StmSession
from neurobooth_os.tasks import Task
from neurobooth_os.util.task_log_entry import TaskLogEntry

import neurobooth_os
from neurobooth_os import config

from neurobooth_os.iout import metadator as meta

from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.log_manager import make_db_logger


prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3


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

    def _finish_tasks(session):
        session.logger.debug('FINISH SCREEN')
        finish_screen(session.win)
        return True

    presented: bool = False
    session: Optional[StmSession] = None
    task_log_entry: Optional[TaskLogEntry] = None
    db_conn = meta.get_database_connection(database=config.neurobooth_config.database.dbname)

    paused: bool = False        # True if message received that RC requests a session pause
    session_canceled = False    # True if message received that RC requests that the session be canceled
    finished = False            # True if the "Thank you" screen has been displayed
    shutdown: bool = False      # True if message received that this server should be terminated
    init_servers = Request(source="STM", destination="CTR", body=ServerStarted())
    meta.post_message(init_servers, db_conn)

    while not shutdown:

        while paused:
            message: Message = meta.read_next_message_while_paused("STM", conn=db_conn)
            if message is None:
                sleep(1)
                continue

            current_msg_type: str = message.msg_type

            # Next message tells what to do now that we paused
            if "TerminateServerRequest" == current_msg_type:
                paused = False
                shutdown = True
                break
            if "ResumeSessionRequest" == current_msg_type:
                paused = False
                break
            elif "CancelSessionRequest" == current_msg_type:
                session_canceled = True
                paused = False
                break
            elif "CalibrationRequest" == current_msg_type:
                if not len(task_calib):
                    continue
                # TODO: Fix this line. There's no insert going on here. Just do the calib task
                tasks.insert(0, task_calib[0])
                calib_instructions = False

                # TODO: validate this logic
                paused = False
                break
            else:
                body = StatusMessage(text=f'"Received an unexpected message while paused: {message.model_dump_json()}')

                err_msg = Request(source='STM', destination='CTR', body=body)
                meta.post_message(err_msg, session.db_conn)
                logger.warn(f"Received an unexpected message while paused {current_msg_type}")
                shutdown = True
                paused = False
                break

        message: Message = meta.read_next_message("STM", conn=db_conn)
        if message is None:
            sleep(1)
            continue

        logger.info(f'MESSAGE RECEIVED: {message.model_dump_json()}')
        logger.info(f'MESSAGE RECEIVED: {message.body.model_dump_json()}')
        current_msg_type: str = message.msg_type

        if "TerminateServerRequest" == current_msg_type:
            if session is not None:
                session.shutdown()
            shutdown = True
            continue

        if not session_canceled:

            if "PrepareRequest" == current_msg_type:
                request: PrepareRequest = message.body
                session, task_log_entry = prepare_session(request, logger)

            elif 'CreateTasksRequest' == current_msg_type:
                # task_name can be list of tk1-task2-task3
                calib_instructions, device_log_entry_dict, subj_id, task_calib, tasks = _create_tasks(logger, message,
                                                                                                      session,
                                                                                                      task_log_entry)
            elif "PerformTaskRequest" == current_msg_type:
                _perform_task(calib_instructions, db_conn, device_log_entry_dict, logger, message, session, subj_id,
                              task_log_entry, tasks)

            elif "PauseSessionRequest" == current_msg_type:
                paused = _pause(session)

            elif "TasksFinished" == current_msg_type:
                session_canceled = True
                # TODO: Should there be an acknowledgement back to CTR

            else:
                unex_msg = f'Unexpected message received: {message.model_dump_json()}'
                logger.error(unex_msg)
                shutdown = True

        if session_canceled and not finished:
            finished = _finish_tasks(session)

    exit()


def _perform_task(calib_instructions, db_conn, device_log_entry_dict, logger, message, session, subj_id, task_log_entry,
                  tasks):
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

            _wait_for_lsl_recording_to_start(db_conn, logger, session, t0)

            _start_acq(calib_instructions, session, task_args, task_id, this_task_kwargs, tsk_start_time)

            this_task_kwargs.update({"last_task": len(tasks) == 0})
            this_task_kwargs["task_name"] = task_id
            this_task_kwargs["subj_id"] += "_" + tsk_start_time

            elapsed_time = time() - t00
            session.logger.info(f"Total TASK WAIT start took: {elapsed_time:.2f}")

            session.logger.debug(f"RUNNING TASK FUNCTION")
            events = task.run(**this_task_kwargs)
            session.logger.debug(f"TASK FUNCTION RETURNED")

            stop_acq(session, task_args)

            # Signal CTR to stop LSL rec
            meta.post_message(Request(source='STM', destination='CTR', body=TaskCompletion(task_id=task_id)),
                              db_conn)
            session.logger.info(f'FINISHED TASK: {task_id}')
            log_task(events, session, task_id, task_id, task_log_entry, task)
            elapsed_time = time() - t00
            session.logger.info(f"Total TASK WAIT stop took: {elapsed_time:.2f}")


def _create_tasks(logger, message, session, task_log_entry):
    msg_body: CreateTasksRequest = message.body
    session.logger.debug(f"Creating Tasks {msg_body.tasks}")
    tasks = msg_body.tasks
    subj_id = msg_body.subj_id
    session_id = msg_body.session_id
    task_log_entry.log_session_id = session_id
    # Preload tasks media
    t0 = time()
    task_list: List[TaskArgs] = []
    for task_id in tasks:
        if task_id in session.tasks():
            task_args: TaskArgs = _get_task_args(session, task_id)
            task_list.append(task_args)
            tsk_fun_obj: Callable = copy.copy(
                task_args.task_constructor_callable)  # callable for Task constructor
            this_task_kwargs = create_task_kwargs(session, task_args)
            task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
    device_log_entry_dict = meta.log_devices(session.db_conn, task_list)
    session.logger.info(f'Task media took {time() - t0:.2f}')
    session.win = welcome_screen(win=session.win)
    task_calib = [t for t in tasks if "calibration_task" in t]
    # Show calibration instruction video only the first time
    calib_instructions = True
    reply_body = TasksCreated()
    reply = Reply(source="STM", destination=message.source, body=reply_body, request_uuid=message.uuid)
    meta.post_message(reply, session.db_conn)
    return calib_instructions, device_log_entry_dict, subj_id, task_calib, tasks


def _wait_for_lsl_recording_to_start(db_conn, logger, session, t0):
    ctr_msg_found: bool = False
    attempt = 0
    while not ctr_msg_found and attempt < 30:
        ctr_msg_found = meta.read_next_message("STM", db_conn, 'LslRecording') is not None
        sleep(1)
        attempt = attempt + 1
    if not ctr_msg_found:
        logger.info("Message LsLRecording not received in STM")
    else:
        logger.info("Message LsLRecording received in STM")
    elapsed_time = time() - t0
    session.logger.info(f'Waiting for LSL startup took: {elapsed_time:.2f}')


def _get_task_args(session: StmSession, task_id: str):
    if session.task_func_dict is None:
        raise RuntimeError("task_func_dict is not set in StmSession")
    return session.task_func_dict[task_id]


def stop_acq(session: StmSession, task_args: TaskArgs):
    """ Stop recording on ACQ in parallel to stopping on STM """
    session.logger.info(f'SENDING record_stop TO ACQ')
    stimulus_id = task_args.stim_args.stimulus_id

    body = StopRecording()
    sr_msg = Request(source="STM", destination='ACQ', body=body)
    meta.post_message(sr_msg, session.db_conn)

    # acq_result = executor.submit(socket_message, "record_stop", "acquisition", wait_data=15)

    # Stop eyetracker
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        if "calibration_task" not in stimulus_id:
            session.eye_tracker.stop()

    acq_reply = None
    attempts = 0
    while acq_reply is None and attempts < 30:
        acq_reply = meta.read_next_message("STM", session.db_conn, msg_type="RecordingStopped")
        # TODO: Handle higher priority msgs
        # TODO: Handle error conditions reported by ACQ -> Consider adding an error field to the RecordingStopped msg
        sleep(1)
        attempts = attempts + 1


def _start_acq(calib_instructions, session: StmSession, task_args: TaskArgs, task_id: str, this_task_kwargs,
               tsk_start_time):
    """
    Start recording on ACQ in parallel to starting on STM

    Parameters
    ----------
    calib_instructions
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

    fname = f"{session.session_name}_{tsk_start_time}_{task_id}"
    body = StartRecording(
        session_name=session.session_name,
        fname=fname,
        task_id=task_id
    )
    sr_msg = StartRecordingMsg(body=body)
    meta.post_message(sr_msg, session.db_conn)

    # acq_result = executor.submit(
    #     # TODO: Replace with new message
    #     # socket_message,
    #     f"record_start::{session.session_name}_{tsk_start_time}_{task_id}::{task_id}",
    #     "acquisition",
    #     wait_data=10,
    # )

    # Start eyetracker if device in task
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        fname = f"{session.path}/{session.session_name}_{tsk_start_time}_{task_id}.edf"
        if "calibration_task" in stimulus_id:  # if not calibration record with start method
            this_task_kwargs.update({"fname": fname, "instructions": calib_instructions})
        else:
            task_args.task_instance.render_image()  # Render image on HostPC/Tablet screen
            session.eye_tracker.start(fname)
    session.device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected
    acq_reply = None
    while acq_reply is None:
        acq_reply = meta.read_next_message("STM", session.db_conn, msg_type="RecordingStarted")
        # TODO: Handle higher priority msgs
        # TODO: Handle error conditions reported by ACQ  -> Consider adding an error field to the RecordingStarted msg
        sleep(1)

    # wait([acq_result])  # Wait for ACQ to finish
    # acq_result.result()  # Raise any exceptions swallowed by the executor


def _pause(session):
    """ Handle session pause """
    pause_screen = utl.create_text_screen(session.win, text="Session Paused")
    utl.present(session.win, pause_screen, waitKeys=False)
    return True


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


def prepare_session(prepare_req: PrepareRequest, logger):
    logger.info("Preparing STM for operation.")
    collection_id = prepare_req.collection_id
    database_name = prepare_req.database_name
    logger.info(f"Database name is {database_name}.")
    task_log_entry = extract_task_log_entry(prepare_req)
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
    updator = Request(source="STM", destination="CTR", body=SessionPrepared())
    meta.post_message(updator, stm_session.db_conn)
    return stm_session, task_log_entry


def create_task_kwargs(session: StmSession, task_args: TaskArgs) -> Dict:
    """ Returns a dictionary of arguments """
    result: Dict
    if task_args.instr_args is not None:
        result = {**session.as_dict(), **dict(task_args.stim_args), **dict(task_args.instr_args)}
    else:
        result = {**session.as_dict(), **dict(task_args.stim_args)}
    return result


def extract_task_log_entry(prepare_req: PrepareRequest):
    """
    Extracts and returns an object containing info encoded in the data argument,
    which is a message from the GUI.

    Parameters
    ----------
    prepare_req

    Returns
    -------
        TaskLogEntry
    """
    # remove the first part of the msg
    log_entry = {}
    log_entry['log_task_id'] = ''
    log_entry['subject_id'] = prepare_req.subject_id
    log_entry['log_session_id'] = None
    log_entry['task_output_files'] = []
    log_entry['collection_id'] = prepare_req.collection_id
    log_entry['subject_id_date'] = prepare_req.session_name()

    return TaskLogEntry(**log_entry)


if __name__ == '__main__':
    main()
