# -*- coding: utf-8 -*-
"""
Session state and controller for Neurobooth.

Phase 1: SessionState dataclass consolidating all mutable state that was
previously spread across module-level globals and local variables in gui().
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from neurobooth_os.util.nb_types import Subject


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
