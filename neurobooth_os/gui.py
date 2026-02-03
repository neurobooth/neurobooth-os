# -*- coding: utf-8 -*-
"""
Runs RC user interface for controlling a neurobooth session
"""
import base64
import os
import os.path as op
import logging
import sys
import time
import threading
from datetime import datetime
from typing import Dict, Optional, List

import cv2
import numpy as np

import FreeSimpleGUI as sg
import liesl
from FreeSimpleGUI import Multiline

import neurobooth_os.current_release as release
import neurobooth_os.current_config as current_config

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets, stream_plotter

from neurobooth_os.layouts import _main_layout, _win_gen, _init_layout, write_task_notes, PREVIEW_AREA
from neurobooth_os.log_manager import make_db_logger, log_message_received
from neurobooth_os.iout.metadator import LogSession
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.split_xdf import split_sens_files, postpone_xdf_split, get_xdf_name
from neurobooth_os.iout import marker_stream
import neurobooth_os.config as cfg
from neurobooth_os.msg.messages import (Message, PrepareRequest, Request, PerformTaskRequest, CreateTasksRequest,
                                        TerminateServerRequest, MsgBody, MbientDisconnected, NewVideoFile,
                                        TaskCompletion, TaskInitialization,
                                        DeviceInitialization, LslRecording,
                                        TasksFinished, FramePreviewRequest,
                                        FramePreviewReply, PauseSessionRequest, ResumeSessionRequest,
                                        CancelSessionRequest, MEDIUM_HIGH_PRIORITY, ServerStarted)
from util.nb_types import Subject

#  State variables used to help ensure in-order GUI steps
running_servers = []
last_task = None
start_pressed = False
session_prepared_count = 0      # How many SessionPrepared messages were received. the number required = node count
auto_frame_preview_device: Optional[str] = None  # which device to use for automated frame previews for every task
gui_release_version: str = ''
gui_config_version: str = ''


class VersionMismatchError(RuntimeError):
    """Raised when Neurobooth versions across servers are inconsistent."""

    def __init__(self, gui_version: str, other_version: str, server: str, error_type: str):
        self.gui_version = gui_version
        self.other_version = other_version
        self.server = server
        self.error_type = error_type
        super().__init__(
            f"Neurobooth installed incorrectly. Error Type is {error_type}. \n\n "
            f"Version mismatch between GUI and {server}: GUI is on {gui_version}, "
            f"and {server} is on {other_version}"
        )


def setup_log(sg_handler=None):
    logger = make_db_logger("", "")
    logger.setLevel(logging.DEBUG)
    if sg_handler:
        logger.addHandler(sg_handler)
    return logger


class Handler(logging.StreamHandler):
    """LogHandler that emits entries to the GUI"""

    def __init__(self):
        logging.StreamHandler.__init__(self)

    def emit(self, record):
        buffer = str(record).strip()
        window['log'].update(value=buffer)


########## Database functions ############


def _get_subject_by_id(window, log_sess, conn, subject_id: str):
    """Returns the subject record corresponding to the provided subject ID"""
    log_sess.subject_id = subject_id.strip()
    subject = meta.get_subject_by_id(conn, subject_id)
    if subject is not None:
        subject_text = (
                f'Subject ID: {subject.subject_id}, {subject.first_name_birth}'
                + f' {subject.last_name_birth} [ {subject.preferred_first_name} {subject.preferred_last_name} ]'
        )

        window["subject_info"].update(subject_text)
        tooltip = f"Birth date: {subject.date_of_birth.strftime('%Y-%m-%d')}"
        window["subject_info"].set_tooltip(tooltip)
        return subject
    else:
        sg.PopupError(f"Subject {subject_id} not found", location=get_popup_location(window))
        window["subject_info"].update('')


def _get_tasks(window, collection_id: str):
    task_obs = meta.get_task_ids_for_collection(collection_id)
    tasks = ", ".join(task_obs)
    window["tasks"].update(task_obs)
    return tasks


def _get_collections(window, study_id: str):
    collection_ids = meta.get_collection_ids(study_id)
    window["collection_id"].update(values=collection_ids)
    return collection_ids


def _create_session_dict(window, log_task, staff_id, subject: Subject, tasks):
    """Create session dictionary."""
    log_task["subject_id"] = subject.subject_id
    dt = datetime.now().strftime("%Y-%m-%d")
    log_task["subject_id-date"] = f'{subject.subject_id}_{dt}'
    log_task["date"] = dt
    subject_id_date = log_task["subject_id-date"]

    window.close()

    return {
        "subject_id": subject.subject_id,
        "subject_dob": subject.date_of_birth.date().isoformat(),
        "first_name": subject.first_name_birth,
        "last_name": subject.last_name_birth,
        "pref_first_name": subject.preferred_first_name,
        "pref_last_name": subject.preferred_last_name,
        "tasks": tasks,
        "staff_id": staff_id,
        "subject_id_date": subject_id_date,
    }


########## Task-related functions ############


def _start_task_presentation(window, task_list: List[str], subject_id: str, session_id: int, steps):
    """Present tasks"""
    global last_task
    window['Start'].update(disabled=True)
    write_output(window, "\nSession started")
    last_task = task_list[-1]
    if len(task_list) > 0:
        msg_body = CreateTasksRequest(
            tasks=task_list,
            subj_id=subject_id,
            session_id=session_id,
            frame_preview_device_id=auto_frame_preview_device)
        msg = Request(
            source='CTR',
            destination='STM',
            body=msg_body
        )
        meta.post_message(msg)
        steps.append("task_started")
    else:
        sg.PopupError("No task selected", location=get_popup_location(window))


def _pause_tasks(window):
    write_output(window, "Pause scheduled. Session will pause after the current task.")
    continue_msg = "Continue tasks"
    stop_msg = "Stop tasks"

    msg_body = PauseSessionRequest()
    req = Request(source="CTR", destination="STM", body=msg_body)
    meta.post_message(req)
    resp = sg.Popup(
        "The session will pause after the current task.\n", title="Pausing session",
        custom_text=(continue_msg, stop_msg),
        location=get_popup_location(window)
    )
    # handle user closing either popup using 'x' instead of making a choice
    if resp == continue_msg or resp is None:
        body = ResumeSessionRequest()
        request = Request(source="CTR", destination="STM", body=body)
        meta.post_message(request)
        write_output(window, "Continue scheduled")
    elif resp == stop_msg:
        _stop_task_dialog(window, resume_on_cancel=True)
    else:
        raise RuntimeError("Unknown Response from Pause Session dialog")


def _stop_task_dialog(window, resume_on_cancel: bool):
    """

    Parameters
    ----------
    window  The main pysimplegui window
    conn    a database connection
    resume_on_cancel    if false, cancel only closes the dialog. If true, a ResumeSession message is sent to the backend
                        This is for situations where the stop dialog is entered from a Pause dialog

    Returns
    -------

    """
    response = sg.popup_ok_cancel("Session will end after the current task completes!  \n\n"
                                  "Press OK to end the session; Cancel to continue the session.\n",
                                  title="Warning",
                                  location=get_popup_location(window))
    if response == "OK":
        write_output(window, "Stop session scheduled. Session will end after the current task.")
        body = CancelSessionRequest()
        request = Request(source="CTR", destination="STM", body=body)
        meta.post_message(request)
        _session_button_state(window, disabled=True)
    else:
        if resume_on_cancel:
            body = ResumeSessionRequest()
            request = Request(source="CTR", destination="STM", body=body)
            meta.post_message(request)
            _session_button_state(window, disabled=False)


def _calibrate(window):
    write_output(window, "Eyetracker recalibration scheduled. Calibration will start after the current task.")
    msg_body = PerformTaskRequest(task_id="calibration_obs_1", priority=MEDIUM_HIGH_PRIORITY)
    msg = Request(source="CTR", destination="STM", body=msg_body)
    meta.post_message(msg)
    sg.Popup("Eyetracker Recalibration will start after the current task.", location=get_popup_location(window))


########## LSL functions ############

def _start_lsl_session(window, inlets, folder=""):
    window.write_event_value("start_lsl_session", "none")

    # Create LSL session
    streamargs = [{"name": n} for n in list(inlets)]
    session = liesl.Session(
        prefix=folder, streamargs=streamargs, mainfolder=cfg.neurobooth_config.control.local_data_dir
    )
    return session


def write_output(window, text: str, text_color: Optional[str] =None):
    key = "-OUTPUT-"
    if key in window.AllKeysDict:
        elem: Multiline = window.find_element(key)
        elem.print(text, text_color=text_color)


def _record_lsl(
        window,
        session,
        subject_id,
        task_id,
        t_obs_id,
        obs_log_id,
        tsk_strt_time
):
    # Start LSL recording
    rec_fname = f"{subject_id}_{tsk_strt_time}_{t_obs_id}"
    session.start_recording(rec_fname)

    msg_body = LslRecording()
    msg_req = Request(source="CTR", destination='STM', body=msg_body)
    meta.post_message(msg_req)

    window["task_title"].update("Running Task:")
    window["task_running"].update(task_id, background_color="red")
    return rec_fname


def _create_lsl_inlet(stream_ids, outlet_values, inlets):
    outlet_name, outlet_id = eval(outlet_values)

    # update the inlet if new or different source_id
    if stream_ids.get(outlet_name) is None or outlet_id != stream_ids[outlet_name]:
        stream_ids[outlet_name] = outlet_id
        inlets.update(create_lsl_inlets({outlet_name: outlet_id}))


def _stop_lsl_and_save(
        window, session, rec_fname, task_id, obs_log_id, t_obs_id, folder
):
    """Stop LSL stream and save"""
    # Stop LSL recording
    session.stop_recording()
    window["task_running"].update(task_id, background_color="green")

    xdf_fname = get_xdf_name(session, rec_fname)
    xdf_path = op.join(folder, xdf_fname)
    t0 = time.time()
    if any([tsk in task_id for tsk in ["hevelius", "MOT", "pursuit"]]):
        # Don't split large files now, just add to a backlog to handle post-session
        postpone_xdf_split(xdf_path, t_obs_id, obs_log_id, cfg.neurobooth_config.split_xdf_backlog)
        write_output(window, f"SPLIT XDF {t_obs_id} took: {time.time() - t0}")
    else:
        # Split XDF in a thread
        with meta.get_database_connection() as db_conn:
            xdf_split = threading.Thread(
                target=split_sens_files,
                args=(xdf_path, obs_log_id, t_obs_id, db_conn),
                daemon=True,
            )
            xdf_split.start()
        write_output(window, f"SPLIT XDF {task_id} took: {time.time() - t0}")


######### Server communication ############


def _start_servers(window, nodes):
    window["-init_servs-"].Update(disabled=True)
    write_output(window, "Starting servers. Please wait....")

    event, values = window.read(0.1)
    ctr_rec.start_servers(nodes=nodes)
    time.sleep(1)
    return event, values


def _start_ctr_server(window, logger):
    """Start threaded control server and new window."""

    # Start a threaded socket CTR server once main window generated
    callback_args = window
    server_thread = threading.Thread(
        target=_start_ctr_msg_reader,
        args=(
            logger,
            callback_args,
        ),
        daemon=True,
    )
    server_thread.start()


def _start_ctr_msg_reader(logger, window):
    global auto_frame_preview_device

    with meta.get_database_connection() as db_conn:
        while True:
            message: Message = meta.read_next_message("CTR", conn=db_conn)
            if message is None:
                time.sleep(.25)
                continue
            msg_body: Optional[MsgBody] = None
            log_message_received(message, logger)

            if "DeviceInitialization" == message.msg_type:
                msg_body: DeviceInitialization = message.body
                outlet_name = msg_body.stream_name
                outlet_id = msg_body.outlet_id
                device_id = msg_body.device_id
                if msg_body.auto_camera_preview:
                    auto_frame_preview_device = device_id
                outlet_values = f"['{outlet_name}', '{outlet_id}']"
                window.write_event_value("-OUTLETID-", outlet_values)
                if msg_body.camera_preview:
                    window.write_event_value("-new_preview_device-", [outlet_name, device_id])
            elif "SessionPrepared" == message.msg_type:
                window.write_event_value("devices_connected", True)
            elif "ServerStarted" == message.msg_type:
                msg_body: ServerStarted = message.body
                server_version = msg_body.neurobooth_version
                server_config_version = msg_body.config_version
                if server_version != gui_release_version:
                    window.write_event_value('-version_error-', [server_version, message.source])
                    return
                if server_config_version != gui_config_version:
                    window.write_event_value('-config_version_error-', [server_config_version, message.source])
                    return
                window.write_event_value("server_started", message.source)
            elif "TasksCreated" == message.msg_type:
                window.write_event_value("tasks_created", "")
            elif "TaskInitialization" == message.msg_type:
                msg_body: TaskInitialization = message.body
                task_id = msg_body.task_id
                log_task_id = msg_body.log_task_id
                tsk_strt_time = msg_body.tsk_start_time

                window.write_event_value(
                    "task_initiated",
                    f"['{task_id}', '{task_id}', '{log_task_id}', '{tsk_strt_time}']",
                )

            elif "TaskCompletion" == message.msg_type:
                msg_body: TaskCompletion = message.body
                task_id = msg_body.task_id
                has_lsl_stream = msg_body.has_lsl_stream
                event_value = f"['{task_id}', '{has_lsl_stream}']"
                logger.debug(f"TaskCompletion msg for {task_id}")
                window.write_event_value("task_finished", event_value)

            elif "NewVideoFile" == message.msg_type:
                msg_body: NewVideoFile = message.body
                event = msg_body.event
                stream_name = msg_body.stream_name
                filename = msg_body.filename
                window.write_event_value(event, f"{stream_name},{filename}")

            elif "NoEyetracker" == message.msg_type:
                window.write_event_value(
                    "no_eyetracker",
                    "Eyetracker not found! \nServers will be "
                    + "terminated, wait until servers are closed.\nThen, connect the eyetracker and start again",
                )

            elif "MbientDisconnected" == message.msg_type:
                msg_body: MbientDisconnected = message.body
                window.write_event_value(
                    "mbient_disconnected", f"{msg_body.warning}, \nconsider repeating the task"
                )
            elif "StatusMessage" == message.msg_type:
                write_message_to_output(logger, message, window)

            elif "ErrorMessage" == message.msg_type:
                write_message_to_output(logger, message, window)

            elif "FramePreviewReply" == message.msg_type:
                frame_reply: FramePreviewReply = message.body
                handle_frame_preview_reply(window, frame_reply)
            else:
                logger.debug(f"Unhandled message: {message.msg_type}")


def report_version_error_and_close(logger, version_error: VersionMismatchError, window):

    heading = "Critical Error: "
    msg = (f"Neurobooth {version_error.error_type} versions are not consistent! "
           f"The system will shutdown when you press OK. \n\n"
           f"The full error was: '{str(version_error)}'")

    result = sg.popup_ok(msg, title=heading, location=get_popup_location(window))
    if result == "OK":
        # User clicked OK
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(version_error)}")


def write_message_to_output(logger, message: Request, window):
    msg_body = message.body
    text_color: Optional[str]
    heading = "Status: "
    msg = msg_body.text
    if msg_body.status is None:
        text_color = "black"
    elif msg_body.status.upper() == "CRITICAL":
        heading = "Critical Error: "
        msg = (f"A critical error has occurred on server '{message.source}'. "
               f"The system must shutdown. Please terminate the system and make sure ACQ and STM "
               f"have shut-down correctly "
               f"before restarting the session.\n"
               f"The error was: '{msg_body.text}'")
        text_color = "red"

    elif msg_body.status.upper() == "ERROR":
        text_color = "red"
    elif msg_body.status == "WARNING":
        text_color = "orange red"
    else:
        text_color = None
    write_output(window=window, text=f"{heading}: {msg}", text_color=text_color)
    logger.debug(msg_body.text)


######### Visualization ############

def _plot_realtime(window, plttr, inlets):
    # if no inlets send event to prepare devices and make popup error
    if len(inlets) == 0:
        window.write_event_value("-Connect-")
        sg.PopupError("No inlet devices detected, preparing. Press plot once prepared",
                      location=get_popup_location(window))

    if plttr.pltotting_ts is True:
        plttr.inlets = inlets
    else:
        plttr.start(inlets)


def enable_frame_preview(window, preview_devices: Dict[str, str]) -> None:
    if not preview_devices:
        return  # No registered devices; do not enable the preview

    available_streams = sorted(list(preview_devices.keys()))

    # Pick the specified default preview device if available, otherwise pick the first entry.
    preview_default = cfg.neurobooth_config.default_preview_stream
    if preview_default not in available_streams:
        preview_default = available_streams[0]

    # Enable the preview button and the Combo picker
    window["-frame_preview-"].update(disabled=False)
    window["-frame_preview_opts-"].update(disabled=False, value=preview_default, values=available_streams)


def handle_frame_preview_reply(window, frame_reply: FramePreviewReply) -> None:
    if not frame_reply.image_available or len(frame_reply.image) < 100:
        write_output(window, f"ERROR: Unable to preview ({frame_reply.unavailable_message})", text_color="red")
        return

    # Decode the image from the message into a NumPy array (OpenCV format)
    frame = base64.b64decode(frame_reply.image)
    nparr = np.frombuffer(frame, dtype=np.uint8)
    img_np = cv2.imdecode(nparr, flags=1)

    img_rz = resize_frame_preview(img_np)

    # Re-encode the image and present it
    img_b = cv2.imencode(".png", img_rz)[1].tobytes()
    window["iphone"].update(data=img_b)


def resize_frame_preview(img: np.ndarray) -> np.ndarray:
    """
    Resize the given image such that its width matches that of the preview area.
    If the resulting image is taller than the preview area, then it is vertically center-cropped.
    """
    h, w, _ = img.shape  # x and y are flipped in OpenCV
    new_w, max_h = PREVIEW_AREA

    # Resize to the desired width
    aspect_ratio = w / h
    new_h = int(round(new_w / aspect_ratio))
    img = cv2.resize(img, (new_w, new_h))

    if new_h > max_h:  # Vertically crop if needed
        crop = (new_h - max_h) // 2
        img = img[crop:-crop, :]

    return img


def _request_frame_preview(conn, device_id: str) -> None:
    msg = FramePreviewRequest(device_id=device_id)
    req = Request(source="CTR", destination="ACQ", body=msg)
    meta.post_message(req, conn)


def _prepare_devices(window, nodes: List[str], collection_id: str, log_task: Dict, database, tasks: str,
                     selected_tasks: List[str], conn):
    """Prepare devices. Mainly ensuring devices are connected"""

    # disable button so it can't be pushed twice, and disable changes to task selection
    window["-Connect-"].Update(disabled=True)
    window['-SELECT_ALL-'].Update(disabled=True)

    task_list: List[str] = tasks.split(',')
    for task in task_list:
        task_checkbox: sg.Checkbox = window.find_element(task.strip())
        task_checkbox.update(disabled=True)

    write_output(window, "\nConnecting devices. Please wait....")

    video_marker_stream = marker_stream("videofiles")

    nodes = ctr_rec._get_nodes(nodes)
    for node in nodes:
        if node == 'acquisition':
            dest = "ACQ"
        else:
            dest = "STM"
        body = PrepareRequest(database_name=database,
                              subject_id=log_task['subject_id'],
                              collection_id=collection_id,
                              selected_tasks=selected_tasks,
                              date=log_task['date']
                              )
        msg = Request(source='CTR',
                      destination=dest,
                      body=body)

        meta.post_message(msg, conn)
    return video_marker_stream


def _get_nodes():
    return ["acquisition", "presentation"]


def display_calibration_key_info(win):
    instructions  = """
Calibration instructions: 
    Press C to trigger calibration mode
    Press ENTER to start calibration
    
    Press V to trigger validation mode
    Press ENTER to start validation
    
    Press ENTER/ESC after successful validation to exit validation mode
    
    Press O to accept calibration
    
    Press ESC to exit calibration or validation mode.
    Pressing ESC outside of these modes ends the calibration task
"""
    for line in instructions.splitlines():
        write_output(win, line)


def gui(logger):
    """Start the Graphical User Interface.
    """
    global running_servers, start_pressed, gui_release_version, gui_config_version

    database = cfg.neurobooth_config.database.dbname

    gui_release_version = release.version
    gui_config_version = current_config.version
    logger.info(f"Neurobooth application version = {gui_release_version}")
    logger.info(f"Neurobooth config version = {gui_config_version}")

    nodes = _get_nodes()

    # declare and initialize vars
    subject: Subject
    task_string: Optional[str] = None       # A comma delimited list of task ids in a string
    frame_preview_devices: Dict[str, str] = {}  # Maps from stream name to device ID

    with meta.get_database_connection() as conn:
        meta.clear_msg_queue(conn)

        window = _win_gen(_init_layout, conn)

        plttr = stream_plotter()
        log_task = meta.new_task_log_dict()
        log_sess = LogSession(application_version=gui_release_version, config_version=gui_config_version)
        stream_ids, inlets = {}, {}
        plot_elem, inlet_keys = [], []
        steps = list()  # keep track of steps done
        event, values = window.read(0.1)
        sess_info = None
        while True:
            event, values = window.read(0.5)
            ############################################################
            # Initial Window -> Select subject, study and tasks
            ############################################################
            if event == "study_id":
                study_id = values[event]
                log_sess.study_id = study_id
                _get_collections(window, study_id)

            elif event == '-version_error-':
                server_version, server = values[event]
                version_error = VersionMismatchError(gui_release_version, server_version, server, "CODE")
                terminate_system(conn, plttr, sess_info, values, window) # kill other servers
                report_version_error_and_close(logger, version_error, window)
                break

            elif event == '-config_version_error-':
                server_config_version, server = values[event]
                version_error = VersionMismatchError(gui_config_version, server_config_version, server,
                                                     "CONFIG")
                terminate_system(conn, plttr, sess_info, values, window) # kill other servers
                report_version_error_and_close(logger, version_error, window)
                break

            elif event == "find_subject":
                subject: Subject = _get_subject_by_id(window, log_sess, conn, values["subject_id"])

            elif event == "collection_id":
                collection_id: str = values[event]
                log_sess.collection_id = collection_id
                task_string = _get_tasks(window, collection_id)

            elif event == "_init_sess_save_":
                if values["study_id"] == "" or values['collection_id'] == "":
                    sg.PopupError("Study and Collection are required fields", location=get_popup_location(window))
                elif values["staff_id"] == "":
                    sg.PopupError("Staff ID is required", location=get_popup_location(window))
                elif window["subject_info"].get() == "":
                    sg.PopupError("Please select a Subject", location=get_popup_location(window))
                else:
                    log_sess.staff_id = values["staff_id"]
                    sess_info = _create_session_dict(
                        window,
                        log_task,
                        values["staff_id"],
                        subject,
                        task_string,
                    )
                    # Open new layout with main window
                    window = _win_gen(_main_layout, sess_info)
                    _start_ctr_server(window, logger)
                    logger.debug(f"ctr msg reader started")

            ############################################################
            # Main Window -> Run neurobooth session
            ############################################################

            # Handle select all/none checkbox
            if event == '-SELECT_ALL-':
                select_all_state = values['-SELECT_ALL-']
                # Update all other checkboxes to match the select all/none state
                all_task_list: List[str] = task_string.split(',')

                for task in all_task_list:
                    task_checkbox: sg.Checkbox = window.find_element(task.strip())
                    task_checkbox.update(value=select_all_state)

            # Start servers on STM, ACQ
            elif event == "-init_servs-":
                _start_servers(window, nodes)

            # Turn on devices
            elif event == "-Connect-":
                event, values = window.read(0.1)
                selected_tasks: List[str] = [k for k, v in values.items() if "obs" in k and v is True]

                if not selected_tasks:
                    sg.popup_error(
                        "You must select at least one task to continue",
                        location=get_popup_location(window)
                    )
                    continue

                video_marker_stream = _prepare_devices(window,
                    nodes, collection_id, log_task, database, task_string, selected_tasks, conn)

            elif event == "plot":
                _plot_realtime(window, plttr, inlets)

            elif event == "Start":
                if not start_pressed:
                    window["Start"].Update(disabled=True)
                    start_pressed = True
                    session_id = meta.make_session_id(conn, log_sess)
                    task_list: List[str] = [k for k, v in values.items() if "obs" in k and v is True]
                    _start_task_presentation(window, task_list, sess_info["subject_id"], session_id, steps)

            elif event == "tasks_created":
                _session_button_state(window, disabled=False)
                for task_id in task_list:
                    msg_body = PerformTaskRequest(task_id=task_id)
                    msg = Request(source="CTR", destination="STM", body=msg_body)
                    meta.post_message(msg, conn)
                # PerformTask Messages queued for all tasks, now queue a TasksFinished message
                msg_body = TasksFinished()
                msg = Request(source="CTR", destination="STM", body=msg_body)
                meta.post_message(msg, conn)

            elif event == "Pause tasks":
                _pause_tasks(window)

            elif event == "Stop tasks":
                _stop_task_dialog(window, resume_on_cancel=False)

            elif event == "Calibrate":
                _calibrate(window)

            # Save notes to a txt
            elif event == "_save_notes_":
                if values["_notes_taskname_"] != "":
                    _save_session_notes(sess_info, values, window)
                else:
                    sg.PopupError(
                        "Pressed save notes without task, select one in the dropdown list",
                        location=get_popup_location(window)
                    )
                    continue

            elif event == sg.WIN_CLOSED:
                break

            # Shut down the other servers and stops plotting
            elif event == "Shut Down" or event == sg.WINDOW_CLOSE_ATTEMPTED_EVENT:
                if (values is not None
                        and ('notes' in values and values['notes'] != '')
                        and ("_notes_taskname_" not in values or values['_notes_taskname_'] == '')):
                    sg.PopupError(
                        "Unsaved notes without task. Before exiting, "
                        "select a task in the dropdown list or delete the note text.",
                        location=get_popup_location(window)
                    )
                    continue
                else:
                    response = sg.popup_ok_cancel("System will terminate!  \n\n"
                                                  "Please ensure that any task in progress is completed and that STM "
                                                  "and ACQ shut down properly.\n", title="Warning",
                                                  location=get_popup_location(window))
                    if response == "OK":
                        write_output(window, "System termination scheduled. "
                                             "Servers will shut down after the current task.")

                        terminate_system(conn, plttr, sess_info, values, window)
                        break

            ##################################################################################
            # Thread events from process_received_data -> received messages from other servers
            ##################################################################################

            # Signal a task started: record LSL data and update gui
            elif event == "task_initiated":
                # event values -> f"['{task_id}', '{t_obs_id}', '{log_task_id}, '{tsk_strt_time}']
                window["-frame_preview-"].update(disabled=True)
                task_id, t_obs_id, obs_log_id, tsk_strt_time = eval(values[event])
                write_output(window, f"\nTask initiated: {task_id}")

                logger.debug(f"Starting LSL for task: {t_obs_id}")
                rec_fname = _record_lsl(
                    window,
                    session,
                    sess_info["subject_id_date"],
                    task_id,
                    t_obs_id,
                    obs_log_id,
                    tsk_strt_time,
                )
                if "calibration" in task_id.lower():
                    display_calibration_key_info(window)

            # Signal a task ended: stop LSL recording and update gui
            elif event == "task_finished":
                task_id, has_lsl_stream = eval(values['task_finished'])
                boolean_value = has_lsl_stream.lower() == 'true'
                if boolean_value:
                    logger.debug(f"Stopping LSL for task: {task_id}")
                    handle_task_finished(conn, obs_log_id, rec_fname, sess_info, session, task_id, values, window)
                if task_id == last_task:
                    _session_button_state(window, disabled=True)
                    write_output(window, "\nSession complete: OK to terminate", 'blue')

            # Send a marker string with the name of the new video file created
            elif event == "-new_filename-":
                video_marker_stream.push_sample([values[event]])

            elif event == 'devices_connected':
                global session_prepared_count
                session_prepared_count += 1
                if session_prepared_count == len(_get_nodes()):
                    session = _start_lsl_session(window, inlets, sess_info["subject_id_date"])
                    enable_frame_preview(window, frame_preview_devices)
                    if not start_pressed:
                        window['Start'].update(disabled=False)
                        write_output(window, "Device connection complete. OK to start session")

            # Create LSL inlet stream
            elif event == "-OUTLETID-":
                _create_lsl_inlet(stream_ids, values[event], inlets)

            elif event == "-new_preview_device-":
                outlet_name, device_id = values[event]
                frame_preview_devices[outlet_name] = device_id

            elif event == "server_started":
                server = values[event]
                write_output(window, f"{server} server started")

                if server == "ACQ":
                    node_name = "acquisition"
                elif server == "STM":
                    node_name = "presentation"
                else:
                    raise RuntimeError(f"Unknown server type: {server} as source of ServerStarted message")

                running_servers.append(node_name)
                expected_servers = _get_nodes()
                check = all(e in running_servers for e in expected_servers)
                if check:
                    write_output(window, "Servers initiated. OK to connect devices.")
                    window["-Connect-"].Update(disabled=False)

            elif event == "no_eyetracker":
                result = sg.PopupError(values[event], location=get_popup_location(window))
                if result == 'Error':
                    window.write_event_value("Shut Down", "Shut Down")

            elif event == "mbient_disconnected":
                sg.PopupError(values[event], non_blocking=True, location=get_popup_location(window))

            ##################################################################################
            # Conditionals handling inlets for plotting and recording
            ##################################################################################

            elif event == "-frame_preview-":
                outlet_name = values["-frame_preview_opts-"]
                device_id = frame_preview_devices[outlet_name]
                _request_frame_preview(conn, device_id)

            # Print LSL inlet names in GUI
            if inlet_keys != list(inlets):
                 inlet_keys = list(inlets)
                 window["inlet_State"].update("\n".join(inlet_keys))
    close(window)


def close(window):
    window.close()
    if "-OUTPUT-" in window.AllKeysDict:
        window["-OUTPUT-"].__del__()
    print("Session terminated")


def terminate_system(conn, plttr, sess_info, values, window):
    if sess_info and values:
        _save_session_notes(sess_info, values, window)
    plttr.stop()
    _session_button_state(window, disabled=True)
    shutdown_acq_msg: Message = Request(source="CTR",
                                        destination="STM",
                                        body=TerminateServerRequest())
    shutdown_stm_msg: Message = Request(source="CTR",
                                        destination="ACQ",
                                        body=TerminateServerRequest())
    meta.post_message(shutdown_acq_msg, conn)
    meta.post_message(shutdown_stm_msg, conn)


def handle_task_finished(conn, obs_log_id, rec_fname, sess_info, session, t_obs_id, values, window):
    _stop_lsl_and_save(
        window,
        session,
        rec_fname,
        t_obs_id,
        obs_log_id,
        t_obs_id,
        sess_info["subject_id_date"],
    )
    write_task_notes(
        sess_info["subject_id_date"], sess_info["staff_id"], t_obs_id, ""
    )
    window["-frame_preview-"].update(disabled=False)


def _save_session_notes(sess_info, values, window):
    if values is None or "_notes_taskname_" not in values:
        return
    _make_session_folder(sess_info)
    if values["_notes_taskname_"] == "All tasks":
        for task in sess_info["tasks"].split(", "):
            if not any([i in task for i in ["intro", "pause"]]):
                write_task_notes(
                    sess_info["subject_id_date"],
                    sess_info["staff_id"],
                    task,
                    values["notes"],
                )
    else:
        write_task_notes(
            sess_info["subject_id_date"],
            sess_info["staff_id"],
            values["_notes_taskname_"],
            values["notes"],
        )
    window["notes"].Update("")


def _make_session_folder(sess_info):
    session_dir = op.join(cfg.neurobooth_config.control.local_data_dir, sess_info['subject_id_date'])
    if not op.exists(session_dir):
        os.mkdir(session_dir)


def _session_button_state(window: object, disabled: bool) -> None:

    # Ensure that we don't try to disable page 2 widgets if they're not yet constructed
    if "Pause tasks" in window.AllKeysDict:

        window["Pause tasks"].update(disabled=disabled)
        window["Stop tasks"].update(disabled=disabled)
        window["Calibrate"].update(disabled=disabled)


def get_popup_location(window):
    if window.was_closed():
        return None
    window_x, window_y = window.current_location()
    center_x = window_x + window.size[0] // 2
    center_y = window_y + window.size[1] // 2
    return center_x, center_y


def main():
    """The starting point of Neurobooth"""
    cfg.load_config_by_service_name("CTR")  # Load Neurobooth-OS configuration
    logger = setup_log(sg_handler=Handler().setLevel(logging.DEBUG))
    exit_code = 0
    try:
        logger.debug("Starting GUI")
        gui(logger)
        logger.debug("Stopping GUI")
    except Exception as argument:
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                        exc_info=sys.exc_info())
        exit_code = 1
    finally:
        logging.shutdown()
        os._exit(exit_code)


if __name__ == "__main__":
    main()
