import logging
import sys
import os
import concurrent.futures
from time import time, sleep
from datetime import datetime
import copy

from typing import Dict, Optional, Callable, List
from psychopy import prefs

from neurobooth_os.iout.stim_param_reader import TaskArgs
from neurobooth_os.msg.messages import Message, CreateTasksRequest, \
    TaskInitialization, Request, TaskCompletion, StartRecordingMsg, StartRecording, SessionPrepared, \
    PrepareRequest, TasksCreated, StopRecording, ServerStarted, ErrorMessage
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

    session: Optional[StmSession] = None
    task_log_entry: Optional[TaskLogEntry] = None
    db_conn = meta.get_database_connection(database=config.neurobooth_config.database.dbname)

    paused: bool = False  # True if message received that RC requests a session pause
    session_canceled = False  # True if message received that RC requests that the session be canceled
    finished = False  # True if the "Thank you" screen has been displayed
    shutdown: bool = False  # True if message received that this server should be terminated
    init_servers = Request(source="STM", destination="CTR", body=ServerStarted())
    meta.post_message(init_servers, db_conn)

    while not shutdown:
        try:
            while paused:
                message: Message = meta.read_next_message("STM", msg_type='paused_msg_types', conn=db_conn)
                if message is None:
                    sleep(1)
                    continue

                logger.info(f'MESSAGE RECEIVED: {message.model_dump_json()}')
                logger.info(f'MESSAGE RECEIVED: {message.body.model_dump_json()}')
                current_msg_type: str = message.msg_type

                # Next message tells what to do now that we paused
                if "TerminateServerRequest" == current_msg_type:
                    paused = False
                    shutdown = True
                    break
                if "ResumeSessionRequest" == current_msg_type:
                    paused = False

                    # display 'preparing next task'
                    root_pckg = neurobooth_os.__path__[0]
                    end_screen = utl.get_end_screen(session.win, root_pckg)

                    # TODO: msg is only needed if we need to do markers around this prepare step.
                    # See task.show_text()
                    msg = "Completed-task"

                    utl.present(
                        session.win,
                        end_screen,
                        audio=None,
                        wait_time=0,
                        win_color=(0, 0, 0),
                        waitKeys=False,
                    )
                    break

                elif "CancelSessionRequest" == current_msg_type:
                    session_canceled = True
                    paused = False
                    break
                else:
                    text = (f'"Received an unexpected message while paused: '
                            f'{message.model_dump_json()}')
                    body = ErrorMessage(text=text, status="CRITICAL")
                    err_msg = Request(source='STM', destination='CTR', body=body)
                    meta.post_message(err_msg, session.db_conn)
                    logger.error(f"Received an unexpected message while paused {current_msg_type}")
                    raise RuntimeError(text)

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
                    device_log_entry_dict, subj_id = _create_tasks(message, session, task_log_entry)

                elif "PerformTaskRequest" == current_msg_type:
                    _perform_task(db_conn, device_log_entry_dict, logger, message, session, subj_id, task_log_entry)

                elif "PauseSessionRequest" == current_msg_type:
                    paused = _pause(session)

                elif "TasksFinished" == current_msg_type:
                    session_canceled = True

                elif "CancelSessionRequest" == current_msg_type:
                    session_canceled = True

                else:
                    unex_msg = f'Unexpected message received: {message.model_dump_json()}'
                    logger.error(unex_msg)
                    raise RuntimeError(unex_msg)

            if session_canceled and not finished:
                finished = _finish_tasks(session)
        except Exception as argument:
            with meta.get_database_connection() as db_conn:
                err_msg = ErrorMessage(status="CRITICAL", text=repr(argument))
                req = Request(body=err_msg, source="STM", destination="CTR")
                meta.post_message(req, db_conn)
            raise argument

    exit()


def _perform_task(db_conn, device_log_entry_dict, logger, message, session, subj_id: str,
                  task_log_entry):
    msg_body = message.body
    task_id: str = msg_body.task_id

    tsk_start_time = datetime.now().strftime("%Hh-%Mm-%Ss")
    if task_id not in session.tasks():
        session.logger.warning(f'Task {task_id} not implemented')
    else:
        t00 = time()
        # get task and params
        task_args: TaskArgs = _get_task_args(session, task_id)
        this_task_kwargs = create_task_kwargs(session, task_args)

        # Do not record if intro instructions
        if "intro_" in task_id or "pause_" in task_id:
            load_task_media(session, task_args)
            task: Task = task_args.task_instance
            task.run(**this_task_kwargs)
            # Signal CTR to stop LSL rec
            meta.post_message(Request(source='STM', destination='CTR',
                                      body=TaskCompletion(task_id=task_id, has_lsl_stream=False)), db_conn)
        else:
            log_task_id = meta.make_new_task_row(session.db_conn, subj_id)
            meta.log_task_params(
                session.db_conn,
                log_task_id,
                device_log_entry_dict,
                session.task_func_dict[task_id]
            )
            task_log_entry.date_times = ("{" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ",")
            task_log_entry.log_task_id = log_task_id

            # Signal CTR to start LSL rec and wait for start confirmation
            session.logger.info(f'STARTING TASK: {task_id}')
            init_task_body = TaskInitialization(task_id=task_id,
                                                log_task_id=log_task_id,
                                                tsk_start_time=tsk_start_time)
            meta.post_message(Request(source='STM', destination='CTR', body=init_task_body), conn=db_conn)
            session.logger.info(f'Initiating task:{task_id}:{task_id}:{log_task_id}:{tsk_start_time}')

            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                future1 = executor.submit(_wait_for_lsl_recording_to_start, db_conn, session)
                future2 = executor.submit(_start_acq, session, task_id, tsk_start_time)
                # Wait for all futures to complete
                concurrent.futures.wait([future1, future2])
            _get_task_instance(session, task_args, task_id, tsk_start_time)

            this_task_kwargs["task_name"] = task_id
            this_task_kwargs["subj_id"] += "_" + tsk_start_time

            elapsed_time = time() - t00
            session.logger.info(f"Total task WAIT took: {elapsed_time:.2f}")
            t01 = time()
            events = task_args.task_instance.run(**this_task_kwargs)
            elapsed_time = time() - t01
            session.logger.info(f"Total task RUN took: {elapsed_time:.2f}")
            stop_acq(session, task_args)

            # Signal CTR to stop LSL rec
            meta.post_message(Request(source='STM', destination='CTR', body=TaskCompletion(task_id=task_id)), db_conn)
            session.logger.info(f'FINISHED TASK: {task_id}')
            log_task(events, session, task_id, task_id, task_log_entry, task_args.task_instance)

            elapsed_time = time() - t00
            session.logger.info(f"Total TASK took: {elapsed_time:.2f}")


def _get_task_instance(session: StmSession, task_args: TaskArgs, task_id, tsk_start_time):
    # Create task instance and load media
    t1 = time()
    tsk_fun_obj: Callable = copy.copy(
        task_args.task_constructor_callable)  # callable for Task constructor
    this_task_kwargs = create_task_kwargs(session, task_args)
    task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
    elapsed_time = time() - t1
    session.logger.info(f'Waiting for task instance creation took: {elapsed_time:.2f}')

    # Start eyetracker if device in task
    # Eyetracker has to start after instance creation so we can render an image to the eyetracker output device
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        fname = f"{session.path}/{session.session_name}_{tsk_start_time}_{task_id}.edf"
        task_args.task_instance.render_image()  # Render image on HostPC/Tablet screen
        session.eye_tracker.start(fname)


def _create_tasks(message , session, task_log_entry):
    msg_body: CreateTasksRequest = message.body
    session.logger.debug(f"Creating Tasks {msg_body.tasks}")
    tasks = msg_body.tasks
    subj_id = msg_body.subj_id
    session_id = msg_body.session_id
    task_log_entry.log_session_id = session_id

    task_list: List[TaskArgs] = []
    for task_id in tasks:
        if task_id in session.tasks():
            setup_task(session, task_id, task_list)

    device_log_entry_dict = meta.log_devices(session.db_conn, task_list)

    session.win = welcome_screen(win=session.win)
    reply_body = TasksCreated()
    reply = Request(source="STM", destination=message.source, body=reply_body)
    meta.post_message(reply, session.db_conn)
    session.logger.debug(task_list)
    return device_log_entry_dict, subj_id


def setup_task(session, task_id, task_list):
    task_args: TaskArgs = _get_task_args(session, task_id)
    task_list.append(task_args)


def load_task_media(session: StmSession, task_args: TaskArgs):
    t1 = time()
    tsk_fun_obj: Callable = copy.copy(
        task_args.task_constructor_callable)  # callable for Task constructor
    this_task_kwargs = create_task_kwargs(session, task_args)
    task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
    elapsed_time = time() - t1
    session.logger.info(f'Waiting for media to load took: {elapsed_time:.2f}')


def _wait_for_lsl_recording_to_start(db_conn, session):
    """
    Polls the database waiting for a message from the GUI saying LSL is recording

    # TODO: Run this in its own thread
    Parameters
    ----------
    db_conn
    logger
    session

    Returns
    -------

    """
    t1 = time()
    ctr_msg_found: bool = False
    attempt = 0
    while not ctr_msg_found and attempt < 30:
        ctr_msg_found = meta.read_next_message("STM", db_conn, 'LslRecording') is not None
        sleep(1)
        attempt = attempt + 1
    if not ctr_msg_found:
        session.logger.warning("Message LsLRecording not received in STM")
    else:
        session.logger.info("Message LsLRecording received in STM")
    elapsed_time = time() - t1
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


def _start_acq(session: StmSession, task_id: str, tsk_start_time):
    """
    Start recording on ACQ in parallel to starting on STM

    Parameters
    ----------
    session
    task_id
    tsk_start_time

    Returns
    -------

    """
    t0 = time()
    session.device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected
    elapsed_time = time() - t0
    session.logger.info(f'Waiting for mbient_reconnect took: {elapsed_time:.2f}')

    t1 = time()
    fname = f"{session.session_name}_{tsk_start_time}_{task_id}"
    body = StartRecording(
        session_name=session.session_name,
        fname=fname,
        task_id=task_id
    )
    sr_msg = StartRecordingMsg(body=body)
    meta.post_message(sr_msg, session.db_conn)

    acq_reply = None
    while acq_reply is None:
        acq_reply = meta.read_next_message("STM", session.db_conn, msg_type="RecordingStarted")
        # TODO: Handle higher priority msgs
        # TODO: Handle error conditions reported by ACQ  -> Consider adding an error field to the RecordingStarted msg
        sleep(1)
    elapsed_time = time() - t1
    session.logger.info(f'Waiting for ACQ to start took: {elapsed_time:.2f}')


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
