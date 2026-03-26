# -*- coding: utf-8 -*-
"""
Runs RC user interface for controlling a neurobooth session
"""
import base64
import os
import os.path as op
import logging
import sys
import time as time_mod
from typing import Dict, Optional, List

import cv2
import numpy as np

import FreeSimpleGUI as sg
from FreeSimpleGUI import Multiline

import neurobooth_os.current_release as release
import neurobooth_os.current_config as current_config

from neurobooth_os.realtime.lsl_plotter import stream_plotter

from neurobooth_os.layouts import _main_layout, _win_gen, _init_layout, write_task_notes, PREVIEW_AREA
from neurobooth_os.log_manager import make_db_logger, make_fallback_logger
from neurobooth_os.iout.metadator import LogSession
import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg
from neurobooth_os.msg.messages import FramePreviewReply
from util.nb_types import Subject
from neurobooth_os.session_controller import (
    SessionState, SessionController, SessionEventListener, VersionMismatchError,
    get_nodes, resize_frame_preview,
    create_session_dict, request_frame_preview,
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


########## GUI Event Listener ############


class GuiEventListener(SessionEventListener):
    """Bridges SessionController events to the FreeSimpleGUI event loop."""

    def __init__(self, window):
        self.window = window

    def set_window(self, window):
        self.window = window

    def on_output(self, text, text_color=None):
        write_output(self.window, text, text_color)

    def on_server_started(self, server):
        self.window.write_event_value("server_started", server)

    def on_all_servers_ready(self):
        write_output(self.window, "Servers initiated. OK to connect devices.")

    def on_devices_prepared(self):
        self.window.write_event_value("devices_connected", True)

    def on_task_initiated(self, task_id, t_obs_id, log_task_id, tsk_start_time):
        self.window.write_event_value(
            "task_initiated",
            f"['{task_id}', '{t_obs_id}', '{log_task_id}', '{tsk_start_time}']")

    def on_task_finished(self, task_id, has_lsl_stream):
        self.window.write_event_value("task_finished", f"['{task_id}', '{has_lsl_stream}']")

    def on_tasks_created(self):
        self.window.write_event_value("tasks_created", "")

    def on_session_complete(self):
        write_output(self.window, "\nSession complete: OK to terminate", 'blue')

    def on_version_error(self, error):
        if error.error_type == "CODE":
            self.window.write_event_value('-version_error-', [error.other_version, error.server])
        else:
            self.window.write_event_value('-config_version_error-', [error.other_version, error.server])

    def on_error(self, message, text_color=None):
        write_output(self.window, message, text_color)

    def on_frame_preview(self, frame_reply):
        handle_frame_preview_reply(self.window, frame_reply)

    def on_new_preview_device(self, stream_name, device_id):
        self.window.write_event_value("-new_preview_device-", [stream_name, device_id])

    def on_inlet_update(self, inlet_keys):
        self.window.write_event_value("-OUTLETID-", inlet_keys)

    def on_no_eyetracker(self, warning):
        self.window.write_event_value("no_eyetracker", warning)

    def on_mbient_disconnected(self, warning):
        self.window.write_event_value("mbient_disconnected", warning)

    def on_new_video_file(self, stream_name, filename, event):
        self.window.write_event_value(event, f"{stream_name},{filename}")

    def prompt_pause_decision(self):
        resp = sg.Popup(
            "The session will pause after the current task.\n", title="Pausing session",
            custom_text=("Continue tasks", "Stop tasks"),
            location=get_popup_location(self.window)
        )
        if resp == "Continue tasks" or resp is None:
            return "continue"
        elif resp == "Stop tasks":
            return "stop"
        else:
            raise RuntimeError("Unknown Response from Pause Session dialog")

    def prompt_stop_confirmation(self, resume_on_cancel):
        response = sg.popup_ok_cancel(
            "Session will end after the current task completes!  \n\n"
            "Press OK to end the session; Cancel to continue the session.\n",
            title="Warning",
            location=get_popup_location(self.window))
        confirmed = response == "OK"
        if confirmed:
            _session_button_state(self.window, disabled=True)
        elif resume_on_cancel:
            _session_button_state(self.window, disabled=False)
        return confirmed

    def prompt_shutdown_confirmation(self):
        response = sg.popup_ok_cancel(
            "System will terminate!  \n\n"
            "Please ensure that any task in progress is completed and that STM "
            "and ACQ shut down properly.\n", title="Warning",
            location=get_popup_location(self.window))
        return response == "OK"


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


########## LSL functions ############

def write_output(window, text: str, text_color: Optional[str] =None):
    key = "-OUTPUT-"
    if key in window.AllKeysDict:
        elem: Multiline = window.find_element(key)
        elem.print(text, text_color=text_color)


######### Server communication ############


def report_version_error_and_close(logger, version_error: VersionMismatchError, window):

    heading = "Critical Error: "
    msg = (f"Neurobooth {version_error.error_type} versions are not consistent! "
           f"The system will shutdown when you press OK. \n\n"
           f"The full error was: '{str(version_error)}'")

    result = sg.popup_ok(msg, title=heading, location=get_popup_location(window))
    if result == "OK":
        # User clicked OK
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(version_error)}")


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

    img_rz = resize_frame_preview(img_np, PREVIEW_AREA)

    # Re-encode the image and present it
    img_b = cv2.imencode(".png", img_rz)[1].tobytes()
    window["iphone"].update(data=img_b)


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
    state = SessionState(
        release_version=release.version,
        config_version=current_config.version,
        log_task=meta.new_task_log_dict(),
    )
    gui_listener = GuiEventListener(None)  # window set after creation
    controller = SessionController(state, logger, listener=gui_listener)

    database = cfg.neurobooth_config.database.dbname

    logger.info(f"Neurobooth application version = {state.release_version}")
    logger.info(f"Neurobooth config version = {state.config_version}")

    nodes = get_nodes()

    with meta.get_database_connection() as conn:
        meta.clear_msg_queue(conn)

        window = _win_gen(_init_layout, conn)
        gui_listener.set_window(window)

        plttr = stream_plotter()
        log_sess = LogSession(application_version=state.release_version, config_version=state.config_version)
        event, values = window.read(0.1)
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
                version_error = VersionMismatchError(state.release_version, server_version, server, "CODE")
                plttr.stop()
                _session_button_state(window, disabled=True)
                controller.terminate_servers(conn)
                report_version_error_and_close(logger, version_error, window)
                break

            elif event == '-config_version_error-':
                server_config_version, server = values[event]
                version_error = VersionMismatchError(state.config_version, server_config_version, server,
                                                     "CONFIG")
                plttr.stop()
                _session_button_state(window, disabled=True)
                controller.terminate_servers(conn)
                report_version_error_and_close(logger, version_error, window)
                break

            elif event == "find_subject":
                state.subject = _get_subject_by_id(window, log_sess, conn, values["subject_id"])

            elif event == "collection_id":
                state.collection_id = values[event]
                log_sess.collection_id = state.collection_id
                state.task_string = _get_tasks(window, state.collection_id)

            elif event == "_init_sess_save_":
                if values["study_id"] == "" or values['collection_id'] == "":
                    sg.PopupError("Study and Collection are required fields", location=get_popup_location(window))
                elif values["staff_id"] == "":
                    sg.PopupError("Staff ID is required", location=get_popup_location(window))
                elif window["subject_info"].get() == "":
                    sg.PopupError("Please select a Subject", location=get_popup_location(window))
                else:
                    log_sess.staff_id = values["staff_id"]
                    state.sess_info = create_session_dict(
                        state.log_task,
                        values["staff_id"],
                        state.subject,
                        state.task_string,
                    )
                    window.close()
                    # Open new layout with main window
                    window = _win_gen(_main_layout, state.sess_info)
                    gui_listener.set_window(window)
                    controller.start_message_reader()
                    logger.debug(f"ctr msg reader started")

            ############################################################
            # Main Window -> Run neurobooth session
            ############################################################

            # Handle select all/none checkbox
            if event == '-SELECT_ALL-':
                select_all_state = values['-SELECT_ALL-']
                # Update all other checkboxes to match the select all/none state
                all_task_list: List[str] = state.task_string.split(',')

                for task in all_task_list:
                    task_checkbox: sg.Checkbox = window.find_element(task.strip())
                    task_checkbox.update(value=select_all_state)

            # Start servers on STM, ACQ
            elif event == "-init_servs-":
                window["-init_servs-"].Update(disabled=True)
                write_output(window, "Starting servers. Please wait....")
                event, values = window.read(0.1)
                controller.start_servers()

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

                window["-Connect-"].Update(disabled=True)
                window['-SELECT_ALL-'].Update(disabled=True)
                task_list_all: List[str] = state.task_string.split(',')
                for task in task_list_all:
                    task_checkbox: sg.Checkbox = window.find_element(task.strip())
                    task_checkbox.update(disabled=True)
                write_output(window, "\nConnecting devices. Please wait....")
                controller.prepare_devices(conn, state.collection_id, selected_tasks)

            elif event == "plot":
                _plot_realtime(window, plttr, state.inlets)

            elif event == "Start":
                if not state.start_pressed:
                    window["Start"].Update(disabled=True)
                    state.start_pressed = True
                    state.session_id = meta.make_session_id(conn, log_sess)
                    state.task_list = [k for k, v in values.items() if "obs" in k and v is True]
                    write_output(window, "\nSession started")
                    if not controller.start_task_presentation(
                            state.sess_info["subject_id"], state.session_id):
                        sg.PopupError("No task selected", location=get_popup_location(window))

            elif event == "tasks_created":
                _session_button_state(window, disabled=False)
                controller.queue_task_messages(conn)

            elif event == "Pause tasks":
                controller.pause_session()

            elif event == "Stop tasks":
                controller.stop_session(resume_on_cancel=False)

            elif event == "Calibrate":
                write_output(window, "Eyetracker recalibration scheduled. "
                             "Calibration will start after the current task.")
                controller.send_recalibrate()
                sg.Popup("Eyetracker Recalibration will start after the current task.",
                         location=get_popup_location(window))

            # Save notes to a txt
            elif event == "_save_notes_":
                if values["_notes_taskname_"] != "":
                    controller.save_notes(state.sess_info, values["_notes_taskname_"], values["notes"])
                    window["notes"].Update("")
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
                    if gui_listener.prompt_shutdown_confirmation():
                        write_output(window, "System termination scheduled. "
                                             "Servers will shut down after the current task.")
                        if state.sess_info and values and "_notes_taskname_" in values:
                            controller.save_notes(state.sess_info, values.get("_notes_taskname_", ""),
                                                  values.get("notes", ""))
                        plttr.stop()
                        _session_button_state(window, disabled=True)
                        controller.terminate_servers(conn)
                        break

            ##################################################################################
            # Thread events from process_received_data -> received messages from other servers
            ##################################################################################

            # Signal a task started: record LSL data and update gui
            elif event == "task_initiated":
                t_evt = time_mod.time()
                # event values -> f"['{task_id}', '{t_obs_id}', '{log_task_id}, '{tsk_strt_time}']
                window["-frame_preview-"].update(disabled=True)
                task_id, t_obs_id, state.obs_log_id, tsk_strt_time = eval(values[event])
                state.current_task_id = task_id
                state.current_t_obs_id = t_obs_id
                state.current_tsk_strt_time = tsk_strt_time
                write_output(window, f"\nTask initiated: {task_id}")

                logger.debug(f"Starting LSL for task: {t_obs_id}")
                controller.start_lsl_recording(
                    state.sess_info["subject_id_date"],
                    task_id, t_obs_id, state.obs_log_id, tsk_strt_time,
                )
                logger.info(f"CTR task_initiated handler took: {time_mod.time() - t_evt:.2f}")
                window["task_title"].update("Running Task:")
                window["task_running"].update(task_id, background_color="red")
                if "calibration" in task_id.lower():
                    display_calibration_key_info(window)

            # Signal a task ended: stop LSL recording and update gui
            elif event == "task_finished":
                t_evt = time_mod.time()
                task_id, has_lsl_stream = eval(values['task_finished'])
                boolean_value = has_lsl_stream.lower() == 'true'
                if boolean_value:
                    logger.debug(f"Stopping LSL for task: {task_id}")
                    controller.stop_lsl_recording(
                        task_id, task_id, state.obs_log_id,
                        state.sess_info["subject_id_date"])
                    logger.info(f"CTR task_finished handler took: {time_mod.time() - t_evt:.2f}")
                    window["task_running"].update(task_id, background_color="green")
                    write_task_notes(state.sess_info["subject_id_date"],
                                     state.sess_info["staff_id"], task_id, "")
                    window["-frame_preview-"].update(disabled=False)
                if task_id == state.last_task:
                    _session_button_state(window, disabled=True)
                    controller._join_lsl_stop()
                    write_output(window, "\nSession complete: OK to terminate", 'blue')

            # Send a marker string with the name of the new video file created
            elif event == "-new_filename-":
                state.video_marker_stream.push_sample([values[event]])

            elif event == 'devices_connected':
                controller.start_lsl_session(state.sess_info["subject_id_date"])
                enable_frame_preview(window, state.frame_preview_devices)
                if not state.start_pressed:
                    window['Start'].update(disabled=False)
                    write_output(window, "Device connection complete. OK to start session")

            # Update inlet display
            elif event == "-OUTLETID-":
                state.inlet_keys = values[event]
                window["inlet_State"].update("\n".join(state.inlet_keys))

            elif event == "-new_preview_device-":
                outlet_name, device_id = values[event]
                state.frame_preview_devices[outlet_name] = device_id

            elif event == "server_started":
                server = values[event]
                write_output(window, f"{server} server started")

                if server.startswith("ACQ_"):
                    idx = int(server.split('_')[1])
                    node_name = f"acquisition_{idx}"
                elif server == "STM":
                    node_name = "presentation"
                else:
                    raise RuntimeError(f"Unknown server type: {server} as source of ServerStarted message")

                state.running_servers.append(node_name)
                expected_servers = get_nodes()
                check = all(e in state.running_servers for e in expected_servers)
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
                device_id = state.frame_preview_devices[outlet_name]
                request_frame_preview(conn, device_id)

            # Print LSL inlet names in GUI
    close(window)


def close(window):
    window.close()
    if "-OUTPUT-" in window.AllKeysDict:
        window["-OUTPUT-"].__del__()
    print("Session terminated")


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
    logger = None
    exit_code = 0
    try:
        cfg.load_config_by_service_name("CTR")  # Load Neurobooth-OS configuration
        logger = setup_log(sg_handler=Handler().setLevel(logging.DEBUG))
        logger.debug("Starting GUI")
        gui(logger)
        logger.debug("Stopping GUI")
    except Exception as argument:
        if logger is None:
            logger = make_fallback_logger()
        logger.critical(f"An uncaught exception occurred. Exiting. Uncaught exception was: {repr(argument)}",
                        exc_info=sys.exc_info())
        exit_code = 1
    finally:
        logging.shutdown()
        os._exit(exit_code)


if __name__ == "__main__":
    main()
