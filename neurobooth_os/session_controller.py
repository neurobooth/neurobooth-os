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

import neurobooth_os.config as cfg
import neurobooth_os.iout.metadator as meta
from neurobooth_os.msg.messages import FramePreviewRequest, Request
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
