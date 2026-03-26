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
    TaskInitialization, Request, TaskCompletion, StartRecording, SessionPrepared, \
    PrepareRequest, TasksCreated, StopRecording, ServerStarted, ErrorMessage
from neurobooth_os.stm_session import StmSession
from neurobooth_os.tasks import Task
from neurobooth_os.util.task_log_entry import TaskLogEntry

import neurobooth_os
import neurobooth_os.current_release as release
import neurobooth_os.current_config as current_config

from neurobooth_os import config

from neurobooth_os.iout import metadator as meta

from neurobooth_os.tasks.welcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.log_manager import make_db_logger, make_fallback_logger, log_message_received

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3
calib_instructions: bool = True  # True if we have not yet performed an eyetracker calibration task
frame_preview_device_id: Optional[str] = None


def main():
    logger = None
    exit_code = 0
    try:
        config.load_config_by_service_name("STM")  # Load Neurobooth-OS configuration
        logger = make_db_logger()  # Initialize logging to default
        logger.debug("Starting STM")
        os.chdir(neurobooth_os.__path__[0])
        run_stm(logger)
        logger.debug("Stopping STM")
    except Exception as argument:
        if logger is None:
            logger = make_fallback_logger()
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                        exc_info=sys.exc_info())
        exit_code = 1
    finally:
        logging.shutdown()
        os._exit(exit_code)


def run_stm(logger):
    global frame_preview_device_id

    def _finish_tasks(session):
        session.logger.debug('FINISH SCREEN')
        finish_screen(session.win, session.session_end_slide)
        return True

    session: Optional[StmSession] = None
    task_log_entry: Optional[TaskLogEntry] = None
    paused: bool = False  # True if message received that RC requests a session pause
    session_canceled: bool = False  # True if message received that RC requests that the session be canceled
    finished: bool = False  # True if the "Thank you" screen has been displayed
    shutdown: bool = False  # True if message received that this server should be terminated
    last_task_finished_time: Optional[float] = None  # For inter-task timing
    init_servers = Request(source="STM", destination="CTR", body=ServerStarted(neurobooth_version=release.version,
                                                                               config_version=current_config.version))
    meta.post_message(init_servers)
    paused_msg_conn = meta.get_database_connection()
    read_msg_conn = meta.get_database_connection()

    while not shutdown:
        try:
            while paused:
                message: Message = (
                    meta.read_next_message("STM", msg_type='paused_msg_types', conn=read_msg_conn))
                if message is None:
                    sleep(.25)
                    continue
                log_message_received(message, logger)
                current_msg_type: str = message.msg_type

                # Next message tells what to do now that we paused
                if "TerminateServerRequest" == current_msg_type:
                    paused = False
                    shutdown = True
                    break
                if "ResumeSessionRequest" == current_msg_type:
                    paused = False

                    # display 'preparing next task'
                    end_screen = utl.load_inter_task_slide(session.win)

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
                    meta.post_message(err_msg)
                    logger.error(f"Received an unexpected message while paused {current_msg_type}")
                    raise RuntimeError(text)

            message: Message = meta.read_next_message("STM", conn=read_msg_conn)
            if message is None:
                sleep(.25)
                continue

            log_message_received(message, logger)
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
                    msg_body: CreateTasksRequest = message.body
                    frame_preview_device_id = msg_body.frame_preview_device_id

                elif "PerformTaskRequest" == current_msg_type:
                    if last_task_finished_time is not None:
                        logger.info(f"Inter-task gap (STM idle): {time() - last_task_finished_time:.2f}")
                    _perform_task(device_log_entry_dict, message, session, subj_id, task_log_entry)
                    last_task_finished_time = time()

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


def _perform_task(device_log_entry_dict, message, session, subj_id: str, task_log_entry):
    global calib_instructions
    msg_body = message.body
    task_id: str = msg_body.task_id
    tsk_start_time = datetime.now().strftime("%Hh-%Mm-%Ss")
    edf_fname = f"{session.path}/{session.session_name}_{tsk_start_time}_{task_id}.edf"

    if task_id not in session.tasks():
        session.logger.warning(f'Task {task_id} not implemented')
    else:
        t00 = time()
        # get task and params
        task_args: TaskArgs = _get_task_args(session, task_id)
        this_task_kwargs = create_task_kwargs(session, task_args)

        # Do not record if non-behavior/pause/break tasks
        if not task_args.record_data:
            load_task_media(session, task_args)
            task: Task = task_args.task_instance
            task.run(**this_task_kwargs)
            # Signal CTR to stop LSL rec
            meta.post_message(Request(source='STM', destination='CTR',
                                      body=TaskCompletion(task_id=task_id, has_lsl_stream=False)))
        else:
            with meta.get_database_connection() as log_conn:

                log_task_id = meta.make_new_task_row(log_conn, subj_id)
                meta.log_task_params(
                    log_conn,
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
            meta.post_message(Request(source='STM', destination='CTR', body=init_task_body))
            session.logger.info(f'Initiating task:{task_id}:{task_id}:{log_task_id}:{tsk_start_time}')

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future1 = executor.submit(_wait_for_lsl_recording_to_start, session)
                future2 = executor.submit(_start_acq, session, task_id, tsk_start_time, frame_preview_device_id)
                # Wait for all futures to complete
                concurrent.futures.wait([future1, future2])
            _get_task_instance(session, task_args, edf_fname)

            this_task_kwargs["task_name"] = task_id
            this_task_kwargs["subj_id"] += "_" + tsk_start_time

            elapsed_time = time() - t00
            session.logger.info(f"Total task WAIT took: {elapsed_time:.2f}")
            t01 = time()
            stimulus_id = task_args.stim_args.stimulus_id
            if "calibration_task" in stimulus_id:  # if not calibration record with start method
                this_task_kwargs.update({"fname": edf_fname, "instructions": calib_instructions})
                calib_instructions = False  # Only show the instructions the first time

            events = task_args.task_instance.run(**this_task_kwargs)
            elapsed_time = time() - t01
            session.logger.info(f"Total task RUN took: {elapsed_time:.2f}")
            t_stop = time()
            stop_acq(session, task_args)
            session.logger.info(f"stop_acq took: {time() - t_stop:.2f}")

            # Signal CTR to stop LSL rec
            meta.post_message(Request(source='STM', destination='CTR', body=TaskCompletion(task_id=task_id)))
            session.logger.info(f'FINISHED TASK: {task_id}')
            t_log = time()
            log_task(events, session, task_id, task_id, task_log_entry, task_args.task_instance)
            session.logger.info(f"log_task took: {time() - t_log:.2f}")

            elapsed_time = time() - t00
            session.logger.info(f"Total TASK took: {elapsed_time:.2f}")


def _get_task_instance(session: StmSession, task_args: TaskArgs, edf_fname):
    """Ensure a task instance exists and start the eyetracker if needed.

    If the instance was pre-constructed during ``_create_tasks``, this
    skips construction entirely and only performs eyetracker setup.
    """
    global calib_instructions

    if task_args.task_instance is None:
        t1 = time()
        tsk_fun_obj: Callable = copy.copy(
            task_args.task_constructor_callable)
        this_task_kwargs = create_task_kwargs(session, task_args)
        task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
        elapsed_time = time() - t1
        session.logger.info(f'Waiting for task instance creation took: {elapsed_time:.2f}')
    else:
        session.logger.info('Using pre-constructed task instance')

    # Start eyetracker if device in task
    # Eyetracker has to start after instance creation so we can render an image to the eyetracker output device
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        stimulus_id = task_args.stim_args.stimulus_id
        if "calibration_task" not in stimulus_id:
            task_args.task_instance.render_image()
            session.eye_tracker.start(edf_fname)

def _create_tasks(message, session, task_log_entry):
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

    device_log_entry_dict = meta.log_devices(None, task_list)

    session.win = welcome_screen(win=session.win, slide=session.session_start_slide)
    reply_body = TasksCreated()
    reply = Request(source="STM", destination=message.source, body=reply_body)
    meta.post_message(reply)
    session.logger.debug(task_list)

    # Pre-construct task instances while the operator reviews the welcome screen.
    # This moves the 2-3.5s per-task construction cost out of the inter-task gap.
    t_pre = time()
    for task_id in tasks:
        if task_id in session.tasks():
            task_args = _get_task_args(session, task_id)
            if task_args.task_instance is None:
                try:
                    tsk_fun_obj: Callable = copy.copy(task_args.task_constructor_callable)
                    kwargs = create_task_kwargs(session, task_args)
                    task_args.task_instance = tsk_fun_obj(**kwargs)
                    session.logger.debug(f"Pre-constructed task: {task_id}")
                except Exception as e:
                    session.logger.warning(f"Failed to pre-construct {task_id}: {e}")
    session.logger.info(f"Pre-construction of {len(tasks)} tasks took: {time() - t_pre:.2f}")

    return device_log_entry_dict, subj_id


def setup_task(session, task_id, task_list):
    task_args: TaskArgs = _get_task_args(session, task_id)
    task_list.append(task_args)


def load_task_media(session: StmSession, task_args: TaskArgs):
    if task_args.task_instance is not None:
        session.logger.info('Using pre-constructed task instance')
        return
    t1 = time()
    tsk_fun_obj: Callable = copy.copy(
        task_args.task_constructor_callable)
    this_task_kwargs = create_task_kwargs(session, task_args)
    task_args.task_instance = tsk_fun_obj(**this_task_kwargs)
    elapsed_time = time() - t1
    session.logger.info(f'Waiting for media to load took: {elapsed_time:.2f}')


def _wait_for_lsl_recording_to_start(session):
    """
    Polls the database waiting for a message from the GUI saying LSL is recording

    # TODO: Run this in its own thread
    Parameters
    ----------
    session

    Returns
    -------

    """
    t1 = time()
    ctr_msg_found: bool = False
    attempt = 0
    with meta.get_database_connection() as db_conn:
        while not ctr_msg_found and attempt < 300:
            ctr_msg_found = meta.read_next_message("STM", db_conn, 'LslRecording') is not None
            sleep(.1)
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
    """ Stop recording on all ACQ servers in parallel to stopping on STM """
    t0 = time()
    session.logger.info(f'SENDING record_stop TO ACQ')
    stimulus_id = task_args.stim_args.stimulus_id

    acq_ids = config.neurobooth_config.all_acq_service_ids()
    for acq_id in acq_ids:
        body = StopRecording()
        sr_msg = Request(source="STM", destination=acq_id, body=body)
        meta.post_message(sr_msg)
    session.logger.info(f"stop_acq: posted StopRecording to {len(acq_ids)} ACQs in {time() - t0:.2f}")

    # Stop eyetracker
    t_eye = time()
    device_ids = [x.device_id for x in task_args.device_args]
    if session.eye_tracker is not None and any("Eyelink" in d for d in device_ids):
        if "calibration_task" not in stimulus_id:
            session.eye_tracker.stop()
            session.logger.info(f"stop_acq: eyetracker stop took: {time() - t_eye:.2f}")

    t_poll = time()
    replies = 0
    attempts = 0
    with meta.get_database_connection() as poll_conn:
        while replies < len(acq_ids) and attempts < 300:
            reply = meta.read_next_message("STM", poll_conn, msg_type="RecordingStopped")
            if reply is not None:
                replies += 1
            else:
                sleep(.1)
                attempts += 1
    session.logger.info(f"stop_acq: poll for {len(acq_ids)} RecordingStopped took: {time() - t_poll:.2f} "
                        f"({replies}/{len(acq_ids)} replies, {attempts} poll attempts)")


def _start_acq(session: StmSession, task_id: str, tsk_start_time, frame_preview_device_id):
    """
    Start recording on all ACQ servers in parallel to starting on STM.

    Parameters
    ----------
    session
    task_id
    tsk_start_time
    frame_preview_device_id

    Returns
    -------
    """
    t1 = time()
    file_name = f"{session.session_name}_{tsk_start_time}_{task_id}"
    acq_ids = config.neurobooth_config.all_acq_service_ids()
    preview_acq_id = None
    if frame_preview_device_id is not None:
        preview_acq_idx = config.neurobooth_config.get_acq_for_device(frame_preview_device_id)
        preview_acq_id = config.neurobooth_config.acq_service_id(preview_acq_idx)
    for acq_id in acq_ids:
        body = StartRecording(
            session_name=session.session_name,
            fname=file_name,
            task_id=task_id,
            frame_preview_device_id=frame_preview_device_id if acq_id == preview_acq_id else None
        )
        sr_msg = Request(source='STM', destination=acq_id, body=body)
        meta.post_message(sr_msg)

    replies = 0
    with meta.get_database_connection() as conn:
        while replies < len(acq_ids):
            reply = meta.read_next_message("STM", conn, msg_type="RecordingStarted")
            if reply is not None:
                replies += 1
            else:
                sleep(.1)
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
    with meta.get_database_connection() as conn:
        meta.fill_task_row(task_log_entry, conn)


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
        selected_tasks=prepare_req.selected_tasks,
        db_conn=meta.get_database_connection(database=database_name),
    )
    #  TODO(larry): See about refactoring so we don't need to create a new logger here.
    #   (continued) We already have a db_logger, it just needs session attributes
    stm_session.logger = make_db_logger(subject_id, stm_session.session_name)
    stm_session.logger.info('LOGGER CREATED FOR SESSION')
    updator = Request(source="STM", destination="CTR", body=SessionPrepared())
    meta.post_message(updator)
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
