# -*- coding: utf-8 -*-
"""
Session state and controller for Neurobooth.

Provides SessionState (consolidated mutable state), SessionEventListener
(callback interface for frontends), and pure control functions that have
no GUI dependency.
"""

import os
import os.path as op
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np
import cv2

import logging
import time as time_mod

import neurobooth_os.config as cfg
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.split_xdf import split_sens_files, postpone_xdf_split, get_xdf_name
from neurobooth_os.msg.messages import (
    Message, FramePreviewRequest, Request, CreateTasksRequest, PerformTaskRequest,
    TerminateServerRequest, PrepareRequest, PauseSessionRequest,
    ResumeSessionRequest, CancelSessionRequest, LslRecording,
    TasksFinished, MEDIUM_HIGH_PRIORITY,
)
from neurobooth_os.netcomm import start_server, kill_pid_txt
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets
from neurobooth_os.util.nb_types import Subject


# ---------------------------------------------------------------------------
# Version validation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Event listener interface
# ---------------------------------------------------------------------------

class SessionEventListener(ABC):
    """Interface that a frontend (GUI, headless, test harness) implements.

    The SessionController calls these methods to communicate events.
    A GUI implementation would update widgets; a headless implementation
    would log or queue events for programmatic consumption.
    """

    @abstractmethod
    def on_output(self, text: str, text_color: Optional[str] = None) -> None:
        """Display or log a status message."""

    @abstractmethod
    def on_server_started(self, server: str) -> None:
        """A remote server has started and passed version checks."""

    @abstractmethod
    def on_all_servers_ready(self) -> None:
        """All expected servers are running. OK to connect devices."""

    @abstractmethod
    def on_devices_prepared(self) -> None:
        """All devices are connected and ready. OK to start session."""

    @abstractmethod
    def on_task_initiated(self, task_id: str, t_obs_id: str,
                          log_task_id: str, tsk_start_time: str) -> None:
        """A task has started on the STM machine."""

    @abstractmethod
    def on_task_finished(self, task_id: str, has_lsl_stream: str,
                         video_files: Dict[str, List[str]]) -> None:
        """A task has completed."""

    @abstractmethod
    def on_tasks_created(self) -> None:
        """STM has acknowledged task creation."""

    @abstractmethod
    def on_session_complete(self) -> None:
        """All tasks have finished."""

    @abstractmethod
    def on_version_error(self, error: 'VersionMismatchError') -> None:
        """A version mismatch was detected between servers."""

    @abstractmethod
    def on_error(self, message: str, text_color: Optional[str] = None) -> None:
        """An error or warning message from a remote server."""

    @abstractmethod
    def on_frame_preview(self, frame_reply) -> None:
        """A camera frame preview reply is available for display."""

    @abstractmethod
    def on_new_preview_device(self, stream_name: str, device_id: str) -> None:
        """A new camera preview device has registered."""

    @abstractmethod
    def on_inlet_update(self, inlet_keys: List[str]) -> None:
        """The set of available LSL inlets has changed."""

    @abstractmethod
    def on_no_eyetracker(self, warning: str) -> None:
        """The Eyelink could not be connected."""

    @abstractmethod
    def on_mbient_disconnected(self, warning: str) -> None:
        """An Mbient device disconnected during a task."""

    @abstractmethod
    def on_message_reader_died(self, error_msg: str) -> None:
        """The background message reader thread has crashed."""

    @abstractmethod
    def prompt_pause_decision(self) -> str:
        """Ask the user whether to continue or stop after a pause.

        Returns:
            "continue" to resume, "stop" to end the session.
        """

    @abstractmethod
    def prompt_stop_confirmation(self, resume_on_cancel: bool) -> bool:
        """Ask the user to confirm stopping the session.

        Returns:
            True to stop, False to cancel (and resume if resume_on_cancel).
        """

    @abstractmethod
    def prompt_shutdown_confirmation(self) -> bool:
        """Ask the user to confirm system shutdown.

        Returns:
            True to proceed with shutdown, False to cancel.
        """


# ---------------------------------------------------------------------------
# Pure control functions (no GUI dependency)
# ---------------------------------------------------------------------------

def get_nodes() -> List[str]:
    """Return the list of server node names from the current config."""
    acq_nodes = [f'acquisition_{i}' for i in range(len(cfg.neurobooth_config.acquisition))]
    return acq_nodes + ['presentation']


def make_session_folder(sess_info: Dict) -> None:
    """Create the session data folder on the CTR machine if it doesn't exist."""
    session_dir = op.join(cfg.neurobooth_config.control.local_data_dir, sess_info['subject_id_date'])
    if not op.exists(session_dir):
        os.mkdir(session_dir)


def resize_frame_preview(img: np.ndarray, preview_area: tuple) -> np.ndarray:
    """Resize an image to fit the preview area, center-cropping if too tall."""
    from neurobooth_os.layouts import PREVIEW_AREA
    h, w, _ = img.shape
    new_w, max_h = preview_area

    aspect_ratio = w / h
    new_h = int(round(new_w / aspect_ratio))
    img = cv2.resize(img, (new_w, new_h))

    if new_h > max_h:
        crop = (new_h - max_h) // 2
        img = img[crop:-crop, :]

    return img


def create_session_dict(log_task: Dict, staff_id: str, subject: Subject, tasks: str) -> Dict:
    """Build the session info dictionary from subject/staff/task data.

    This is pure data construction with no GUI dependency. The caller is
    responsible for closing the init window afterward.
    """
    log_task["subject_id"] = subject.subject_id
    dt = datetime.now().strftime("%Y-%m-%d")
    log_task["subject_id-date"] = f'{subject.subject_id}_{dt}'
    log_task["date"] = dt
    subject_id_date = log_task["subject_id-date"]

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


def create_lsl_inlet(stream_ids: Dict, outlet_values: str, inlets: Dict) -> None:
    """Register or update an LSL inlet from a DeviceInitialization message."""
    outlet_name, outlet_id = eval(outlet_values)

    if stream_ids.get(outlet_name) is None or outlet_id != stream_ids[outlet_name]:
        stream_ids[outlet_name] = outlet_id
        inlets.update(create_lsl_inlets({outlet_name: outlet_id}))


def request_frame_preview(conn, device_id: str) -> None:
    """Send a FramePreviewRequest to the ACQ server that owns the device."""
    acq_idx = cfg.neurobooth_config.get_acq_for_device(device_id)
    acq_id = cfg.neurobooth_config.acq_service_id(acq_idx)
    msg = FramePreviewRequest(device_id=device_id)
    req = Request(source="CTR", destination=acq_id, body=msg)
    meta.post_message(req, conn)


@dataclass
class SessionState:
    """All mutable state for a Neurobooth session.

    Replaces the module-level globals and key local variables that were
    previously scattered across gui.py.
    """

    # Server tracking (was: module-level globals)
    running_servers: List[str] = field(default_factory=list)
    last_task: Optional[str] = None
    start_pressed: bool = False
    session_prepared_count: int = 0
    auto_frame_preview_device: Optional[str] = None

    # Version info (was: module-level globals)
    release_version: str = ''
    config_version: str = ''

    # Session setup (was: locals in gui())
    subject: Optional[Subject] = None
    task_string: Optional[str] = None
    collection_id: Optional[str] = None
    sess_info: Optional[Dict] = None
    session_id: Optional[int] = None
    log_task: Optional[Dict] = None
    task_list: List[str] = field(default_factory=list)

    # LSL / recording (was: locals in gui())
    stream_ids: Dict = field(default_factory=dict)
    inlets: Dict = field(default_factory=dict)
    inlet_keys: List = field(default_factory=list)
    session: object = None  # liesl.Session, typed as object to avoid import dependency
    rec_fname: Optional[str] = None
    obs_log_id: Optional[str] = None
    task_video_files: Dict[str, List[str]] = field(default_factory=dict)

    # Device tracking
    frame_preview_devices: Dict[str, str] = field(default_factory=dict)

    # Workflow tracking
    steps: List[str] = field(default_factory=list)

    # Per-task state set during task_initiated, consumed during task_finished
    current_task_id: Optional[str] = None
    current_t_obs_id: Optional[str] = None
    current_tsk_strt_time: Optional[str] = None


# ---------------------------------------------------------------------------
# Session Controller
# ---------------------------------------------------------------------------

class SessionController:
    """Orchestrates a Neurobooth session without any GUI dependency.

    The controller owns the SessionState and provides methods for each
    phase of a session. GUI updates are communicated via a logger; the
    caller (gui.py) handles widget manipulation before/after calling
    controller methods.
    """

    def __init__(self, state: SessionState, logger: logging.Logger,
                 listener: Optional[SessionEventListener] = None):
        self.state = state
        self.logger = logger
        self.listener = listener
        self._lsl_stop_thread: Optional[object] = None  # Background thread for LSL stop

    # --- Server lifecycle ---

    def start_servers(self) -> None:
        """Kill stale server processes and start fresh ones."""
        kill_pid_txt()
        for node in get_nodes():
            if node.startswith('acquisition_'):
                idx = int(node.split('_')[1])
                start_server(node, acq_index=idx)
            else:
                start_server(node)
        time_mod.sleep(1)

    def terminate_servers(self, conn) -> None:
        """Send TerminateServerRequest to STM and all ACQ servers."""
        self._join_lsl_stop()
        shutdown_stm = Request(source="CTR", destination="STM",
                               body=TerminateServerRequest())
        meta.post_message(shutdown_stm, conn)
        for acq_id in cfg.neurobooth_config.all_acq_service_ids():
            shutdown_acq = Request(source="CTR", destination=acq_id,
                                   body=TerminateServerRequest())
            meta.post_message(shutdown_acq, conn)

    def _join_lsl_stop(self, timeout: float = 10.0) -> None:
        """Wait for any in-flight LSL stop to complete."""
        if self._lsl_stop_thread is not None and self._lsl_stop_thread.is_alive():
            self.logger.info("Waiting for background LSL stop to complete...")
            self._lsl_stop_thread.join(timeout=timeout)
            if self._lsl_stop_thread.is_alive():
                self.logger.warning("Background LSL stop did not complete within timeout")

    # --- Device preparation ---

    def prepare_devices(self, conn, collection_id: str, selected_tasks: List[str]) -> None:
        """Send PrepareRequest to all server nodes."""
        database = cfg.neurobooth_config.database.dbname

        for node in get_nodes():
            if node.startswith('acquisition_'):
                idx = int(node.split('_')[1])
                dest = cfg.neurobooth_config.acq_service_id(idx)
            else:
                dest = "STM"
            body = PrepareRequest(
                database_name=database,
                subject_id=self.state.log_task['subject_id'],
                collection_id=collection_id,
                selected_tasks=selected_tasks,
                date=self.state.log_task['date'],
            )
            msg = Request(source='CTR', destination=dest, body=body)
            meta.post_message(msg, conn)

    # --- Session execution ---

    def start_task_presentation(self, subject_id: str, session_id: int) -> bool:
        """Send CreateTasksRequest to STM. Returns False if no tasks selected."""
        if not self.state.task_list:
            return False
        self.state.last_task = self.state.task_list[-1]
        msg_body = CreateTasksRequest(
            tasks=self.state.task_list,
            subj_id=subject_id,
            session_id=session_id,
            frame_preview_device_id=self.state.auto_frame_preview_device,
        )
        msg = Request(source='CTR', destination='STM', body=msg_body)
        meta.post_message(msg)
        self.state.steps.append("task_started")
        return True

    def queue_task_messages(self, conn) -> None:
        """Post PerformTaskRequest for each task, followed by TasksFinished."""
        for task_id in self.state.task_list:
            msg = Request(source="CTR", destination="STM",
                          body=PerformTaskRequest(task_id=task_id))
            meta.post_message(msg, conn)
        msg = Request(source="CTR", destination="STM", body=TasksFinished())
        meta.post_message(msg, conn)

    def send_pause(self) -> None:
        """Send PauseSessionRequest to STM."""
        meta.post_message(Request(source="CTR", destination="STM",
                                  body=PauseSessionRequest()))

    def send_resume(self) -> None:
        """Send ResumeSessionRequest to STM."""
        meta.post_message(Request(source="CTR", destination="STM",
                                  body=ResumeSessionRequest()))

    def send_cancel(self) -> None:
        """Send CancelSessionRequest to STM."""
        meta.post_message(Request(source="CTR", destination="STM",
                                  body=CancelSessionRequest()))

    def pause_session(self) -> None:
        """Pause the session and prompt the user for what to do next.

        Sends PauseSessionRequest, then asks the listener whether to
        continue or stop. Handles the full pause/resume/cancel flow.
        """
        self.listener.on_output("Pause scheduled. Session will pause after the current task.")
        self.send_pause()
        decision = self.listener.prompt_pause_decision()
        if decision == "continue":
            self.send_resume()
            self.listener.on_output("Continue scheduled")
        elif decision == "stop":
            self.stop_session(resume_on_cancel=True)
        else:
            raise RuntimeError(f"Unknown pause decision: {decision}")

    def stop_session(self, resume_on_cancel: bool = False) -> None:
        """Prompt to confirm session stop, then cancel or resume.

        Args:
            resume_on_cancel: If True and the user cancels the stop,
                send ResumeSessionRequest (used when entering stop from pause).
        """
        confirmed = self.listener.prompt_stop_confirmation(resume_on_cancel)
        if confirmed:
            self.listener.on_output("Stop session scheduled. Session will end after the current task.")
            self.send_cancel()
        elif resume_on_cancel:
            self.send_resume()

    def send_recalibrate(self) -> None:
        """Queue a calibration task at elevated priority."""
        msg = Request(source="CTR", destination="STM",
                      body=PerformTaskRequest(task_id="calibration_obs_1",
                                              priority=MEDIUM_HIGH_PRIORITY))
        meta.post_message(msg)

    # --- LSL recording ---

    def start_lsl_session(self, folder: str) -> None:
        """Create an LSL recording session."""
        import liesl
        streamargs = [{"name": n} for n in list(self.state.inlets)]
        self.state.session = liesl.Session(
            prefix=folder,
            streamargs=streamargs,
            mainfolder=cfg.neurobooth_config.control.local_data_dir,
        )

    def start_lsl_recording(self, subject_id: str, task_id: str,
                            t_obs_id: str, obs_log_id: str,
                            tsk_strt_time: str) -> str:
        """Start recording LSL data for a task and notify STM."""
        rec_fname = f"{subject_id}_{tsk_strt_time}_{t_obs_id}"
        t0 = time_mod.time()
        self.state.session.start_recording(rec_fname)
        self.logger.info(f"liesl start_recording took: {time_mod.time() - t0:.2f}")

        msg = Request(source="CTR", destination='STM', body=LslRecording())
        meta.post_message(msg)

        self.state.rec_fname = rec_fname
        self.state.obs_log_id = obs_log_id
        return rec_fname

    def stop_lsl_recording(self, task_id: str, t_obs_id: str,
                           obs_log_id: str, folder: str,
                           video_files: Optional[Dict[str, List[str]]] = None,
                           ) -> None:
        """Stop LSL recording in the background and trigger XDF split.

        The underlying LabRecorderCLI subprocess takes 3-5s to finalize
        the XDF file.  Rather than blocking the GUI event loop (which
        would delay the next task's ``start_lsl_recording``), we capture
        the old subprocess handle and finalize it in a background thread.
        ``start_lsl_recording`` spawns a *new* LabRecorderCLI process, so
        the two can safely run concurrently.

        Args:
            video_files: Pre-snapshotted mapping of stream name to file
                basenames, captured by the message reader thread at
                TaskCompletion time to avoid a race with RecordingFiles
                for the next task.
        """
        import threading as threading_mod

        session = self.state.session
        recorder = session.recorder

        # Capture the old LabRecorderCLI subprocess and timing info
        old_process = recorder.process
        old_t0 = recorder.t0

        # Reset session state immediately so start_recording can proceed
        del recorder.process
        session._is_recording = False

        # Resolve the XDF path now, while state is still current
        xdf_fname = get_xdf_name(session, self.state.rec_fname)
        xdf_path = op.join(folder, xdf_fname)

        # Use the pre-snapshotted video files from the message reader
        # thread (captured atomically at TaskCompletion time).
        if video_files is None:
            video_files = {}

        def _finalize():
            """Finalize the old LabRecorderCLI process and split the XDF."""
            t_stop = time_mod.time()
            try:
                o, e = old_process.communicate(b"\n")
                if old_process.poll() != 0:
                    self.logger.error(
                        f"LabRecorderCLI exited with code {old_process.poll()}: {o} {e}")
                recorder.dur = time_mod.time() - old_t0
            except Exception as exc:
                self.logger.error(f"Error finalizing LabRecorderCLI: {exc}")
            self.logger.info(f"liesl stop_recording took: {time_mod.time() - t_stop:.2f}")

            if any(tsk in task_id for tsk in ["hevelius", "MOT", "pursuit"]):
                postpone_xdf_split(xdf_path, t_obs_id, obs_log_id,
                                   cfg.neurobooth_config.split_xdf_backlog,
                                   video_files=video_files)
            else:
                db_conn = meta.get_database_connection()
                split_thread = threading_mod.Thread(
                    target=self._split_and_close,
                    args=(xdf_path, obs_log_id, t_obs_id, db_conn, video_files),
                    daemon=True,
                )
                split_thread.start()

        self._lsl_stop_thread = threading_mod.Thread(
            target=_finalize, daemon=True, name="lsl-stop")
        self._lsl_stop_thread.start()

    @staticmethod
    def _split_and_close(xdf_path, obs_log_id, t_obs_id, db_conn, video_files=None):
        """Run split_sens_files and close the connection when done."""
        try:
            split_sens_files(xdf_path, obs_log_id, t_obs_id, db_conn,
                             video_files=video_files)
        finally:
            db_conn.close()

    # --- Notes ---

    def save_notes(self, sess_info: Dict, task_name: str, notes_text: str) -> None:
        """Save session notes for a task or all tasks."""
        from neurobooth_os.layouts import write_task_notes
        make_session_folder(sess_info)
        if task_name == "All tasks":
            for task in sess_info["tasks"].split(", "):
                if not any(i in task for i in ["intro", "pause"]):
                    write_task_notes(sess_info["subject_id_date"],
                                     sess_info["staff_id"], task, notes_text)
        else:
            write_task_notes(sess_info["subject_id_date"],
                             sess_info["staff_id"], task_name, notes_text)

    # --- Message reader ---

    def start_message_reader(self) -> None:
        """Start the background thread that polls the DB for CTR messages."""
        import threading
        thread = threading.Thread(target=self._message_reader, daemon=True)
        thread.start()

    def _message_reader(self) -> None:
        """Poll the database for messages and dispatch to the listener."""
        from neurobooth_os.log_manager import log_message_received

        try:
            self._message_reader_loop(log_message_received)
        except Exception as e:
            self.logger.critical(f"Message reader thread died: {e}", exc_info=True)
            try:
                self.listener.on_message_reader_died(str(e))
            except Exception:
                pass  # If even notification fails, at least we logged it

    def _message_reader_loop(self, log_message_received) -> None:
        """Inner loop for _message_reader, separated to allow top-level exception handling."""
        with meta.get_database_connection() as db_conn:
            while True:
                message: Message = meta.read_next_message("CTR", conn=db_conn)
                if message is None:
                    time_mod.sleep(.25)
                    continue

                log_message_received(message, self.logger)

                if "DeviceInitialization" == message.msg_type:
                    body = message.body
                    if body.auto_camera_preview:
                        self.state.auto_frame_preview_device = body.device_id
                    outlet_values = f"['{body.stream_name}', '{body.outlet_id}']"
                    create_lsl_inlet(self.state.stream_ids, outlet_values, self.state.inlets)
                    self.listener.on_inlet_update(list(self.state.inlets.keys()))
                    if body.camera_preview:
                        self.listener.on_new_preview_device(body.stream_name, body.device_id)

                elif "SessionPrepared" == message.msg_type:
                    self.state.session_prepared_count += 1
                    if self.state.session_prepared_count == len(get_nodes()):
                        self.listener.on_devices_prepared()

                elif "ServerStarted" == message.msg_type:
                    body = message.body
                    if body.neurobooth_version != self.state.release_version:
                        self.listener.on_version_error(
                            VersionMismatchError(self.state.release_version,
                                                 body.neurobooth_version, message.source, "CODE"))
                        return
                    if body.config_version != self.state.config_version:
                        self.listener.on_version_error(
                            VersionMismatchError(self.state.config_version,
                                                 body.config_version, message.source, "CONFIG"))
                        return
                    self.listener.on_server_started(message.source)

                elif "TasksCreated" == message.msg_type:
                    self.listener.on_tasks_created()

                elif "TaskInitialization" == message.msg_type:
                    body = message.body
                    self.listener.on_task_initiated(body.task_id, body.task_id,
                                                    body.log_task_id, body.tsk_start_time)

                elif "TaskCompletion" == message.msg_type:
                    body = message.body
                    # Snapshot and clear video files NOW, on the message reader
                    # thread, before the next message can be read.  This prevents
                    # a race where RecordingFiles for the NEXT task is buffered
                    # before the GUI thread calls stop_lsl_recording, causing the
                    # current task to steal the next task's files.
                    video_files = dict(self.state.task_video_files)
                    self.state.task_video_files.clear()
                    self.logger.debug(
                        f"TaskCompletion msg for {body.task_id}, "
                        f"video_files={list(video_files.keys())}")
                    self.listener.on_task_finished(
                        body.task_id, str(body.has_lsl_stream), video_files)

                elif "RecordingFiles" == message.msg_type:
                    body = message.body
                    for stream_name, filenames in body.files.items():
                        existing = self.state.task_video_files.get(stream_name, [])
                        self.state.task_video_files[stream_name] = existing + filenames
                    self.logger.debug(f"Buffered recording files: {body.files}")

                elif "NoEyetracker" == message.msg_type:
                    self.listener.on_no_eyetracker(
                        "Eyetracker not found! \nServers will be terminated, "
                        "wait until servers are closed.\nThen, connect the eyetracker and start again")

                elif "MbientDisconnected" == message.msg_type:
                    body = message.body
                    self.listener.on_mbient_disconnected(
                        f"{body.warning}, \nconsider repeating the task")

                elif "StatusMessage" == message.msg_type:
                    self._handle_status_message(message)

                elif "ErrorMessage" == message.msg_type:
                    self._handle_status_message(message)

                elif "FramePreviewReply" == message.msg_type:
                    self.listener.on_frame_preview(message.body)

                else:
                    self.logger.debug(f"Unhandled message: {message.msg_type}")

    def _handle_status_message(self, message) -> None:
        """Parse status/error messages and forward to listener."""
        body = message.body
        heading = "Status: "
        msg = body.text
        text_color = None

        if body.status is None:
            text_color = "black"
        elif body.status.upper() == "CRITICAL":
            heading = "Critical Error: "
            msg = (f"A critical error has occurred on server '{message.source}'. "
                   f"The system must shutdown. Please terminate the system and make sure ACQ and STM "
                   f"have shut-down correctly before restarting the session.\n"
                   f"The error was: '{body.text}'")
            text_color = "red"
        elif body.status.upper() == "ERROR":
            text_color = "red"
        elif body.status == "WARNING":
            text_color = "orange red"

        self.listener.on_error(f"{heading}: {msg}", text_color=text_color)
        self.logger.debug(body.text)
