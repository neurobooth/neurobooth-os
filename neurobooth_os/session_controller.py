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
    FramePreviewRequest, Request, CreateTasksRequest, PerformTaskRequest,
    TerminateServerRequest, PrepareRequest, PauseSessionRequest,
    ResumeSessionRequest, CancelSessionRequest, LslRecording,
    TasksFinished, MEDIUM_HIGH_PRIORITY,
)
from neurobooth_os.netcomm import start_server, kill_pid_txt
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets
from neurobooth_os.util.nb_types import Subject
from neurobooth_os.iout import marker_stream


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
    def on_task_initiated(self, task_id: str) -> None:
        """A task has started on the STM machine."""

    @abstractmethod
    def on_task_finished(self, task_id: str) -> None:
        """A task has completed."""

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
    def on_frame_preview(self, image_bytes: bytes) -> None:
        """A camera frame preview image is available for display."""

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
    video_marker_stream: object = None

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

    def __init__(self, state: SessionState, logger: logging.Logger):
        self.state = state
        self.logger = logger

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
        shutdown_stm = Request(source="CTR", destination="STM",
                               body=TerminateServerRequest())
        meta.post_message(shutdown_stm, conn)
        for acq_id in cfg.neurobooth_config.all_acq_service_ids():
            shutdown_acq = Request(source="CTR", destination=acq_id,
                                   body=TerminateServerRequest())
            meta.post_message(shutdown_acq, conn)

    # --- Device preparation ---

    def prepare_devices(self, conn, collection_id: str, selected_tasks: List[str]) -> None:
        """Send PrepareRequest to all server nodes and create the video marker stream."""
        database = cfg.neurobooth_config.database.dbname
        self.state.video_marker_stream = marker_stream("videofiles")

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
        self.state.session.start_recording(rec_fname)

        msg = Request(source="CTR", destination='STM', body=LslRecording())
        meta.post_message(msg)

        self.state.rec_fname = rec_fname
        self.state.obs_log_id = obs_log_id
        return rec_fname

    def stop_lsl_recording(self, task_id: str, t_obs_id: str,
                           obs_log_id: str, folder: str) -> float:
        """Stop LSL recording and trigger XDF split."""
        import threading as threading_mod
        self.state.session.stop_recording()

        xdf_fname = get_xdf_name(self.state.session, self.state.rec_fname)
        xdf_path = op.join(folder, xdf_fname)
        t0 = time_mod.time()

        if any(tsk in task_id for tsk in ["hevelius", "MOT", "pursuit"]):
            postpone_xdf_split(xdf_path, t_obs_id, obs_log_id,
                               cfg.neurobooth_config.split_xdf_backlog)
        else:
            with meta.get_database_connection() as db_conn:
                xdf_split = threading_mod.Thread(
                    target=split_sens_files,
                    args=(xdf_path, obs_log_id, t_obs_id, db_conn),
                    daemon=True,
                )
                xdf_split.start()

        return time_mod.time() - t0

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
