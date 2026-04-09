# -*- coding: utf-8 -*-
"""
Headless SessionEventListener for driving Neurobooth sessions without a GUI.

Logs all events and returns default decisions for prompts. Useful for
automated testing, scripted sessions, and verifying that the controller
has no GUI dependency.

Example usage::

    import logging
    import neurobooth_os.config as cfg
    import neurobooth_os.iout.metadator as meta
    from neurobooth_os.session_controller import SessionState, SessionController
    from neurobooth_os.headless_listener import HeadlessListener

    logging.basicConfig(level=logging.INFO)
    cfg.load_neurobooth_config()

    state = SessionState(
        release_version="v0.63.1",
        config_version="v0.63.0",
        log_task=meta.new_task_log_dict(),
    )
    listener = HeadlessListener()
    controller = SessionController(state, logging.getLogger(), listener=listener)

    # Look up a subject
    with meta.get_database_connection() as conn:
        subject = meta.get_subject_by_id(conn, "100123")

    # Create a session
    from neurobooth_os.session_controller import create_session_dict
    state.subject = subject
    state.sess_info = create_session_dict(
        state.log_task, "staff_name", subject, "task1, task2"
    )

    # Start servers and devices
    controller.start_servers()
    controller.start_message_reader()
    # ... wait for on_all_servers_ready ...
    # controller.prepare_devices(conn, "mvp_030", ["task1", "task2"])
    # ... wait for on_devices_prepared ...
    # controller.start_lsl_session(state.sess_info["subject_id_date"])
    # controller.start_task_presentation(subject.subject_id, session_id)
    # controller.queue_task_messages(conn)
    # ... tasks run, events logged by HeadlessListener ...
    # controller.terminate_servers(conn)
"""

import logging
from typing import List, Optional

from neurobooth_os.session_controller import SessionEventListener

logger = logging.getLogger(__name__)


class HeadlessListener(SessionEventListener):
    """A SessionEventListener that logs events and makes automatic decisions."""

    def on_output(self, text: str, text_color: Optional[str] = None) -> None:
        logger.info(text)

    def on_server_started(self, server: str) -> None:
        logger.info(f"Server started: {server}")

    def on_all_servers_ready(self) -> None:
        logger.info("All servers ready")

    def on_devices_prepared(self) -> None:
        logger.info("Devices prepared")

    def on_task_initiated(self, task_id: str, t_obs_id: str,
                          log_task_id: str, tsk_start_time: str) -> None:
        logger.info(f"Task initiated: {task_id}")

    def on_task_finished(self, task_id: str, has_lsl_stream: str,
                         video_files=None) -> None:
        logger.info(f"Task finished: {task_id} (lsl={has_lsl_stream})")

    def on_tasks_created(self) -> None:
        logger.info("Tasks created")

    def on_session_complete(self) -> None:
        logger.info("Session complete")

    def on_version_error(self, error) -> None:
        logger.error(f"Version mismatch: {error}")

    def on_error(self, message: str, text_color: Optional[str] = None) -> None:
        logger.error(message)

    def on_frame_preview(self, frame_reply) -> None:
        logger.debug("Frame preview received")

    def on_new_preview_device(self, stream_name: str, device_id: str) -> None:
        logger.debug(f"Preview device: {stream_name} -> {device_id}")

    def on_inlet_update(self, inlet_keys: List[str]) -> None:
        logger.debug(f"Inlets: {inlet_keys}")

    def on_no_eyetracker(self, warning: str) -> None:
        logger.warning(f"No eyetracker: {warning}")

    def on_mbient_disconnected(self, warning: str) -> None:
        logger.warning(f"Mbient disconnected: {warning}")

    def on_message_reader_died(self, error_msg: str) -> None:
        logger.critical(f"Message reader thread died: {error_msg}")

    def prompt_pause_decision(self) -> str:
        logger.info("Pause decision: auto-continuing")
        return "continue"

    def prompt_stop_confirmation(self, resume_on_cancel: bool) -> bool:
        logger.info("Stop confirmation: auto-declining")
        return False

    def prompt_shutdown_confirmation(self) -> bool:
        logger.info("Shutdown confirmation: auto-confirming")
        return True
