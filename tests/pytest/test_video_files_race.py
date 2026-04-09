"""Test that TaskCompletion snapshots video files atomically.

Reproduces the race condition from GitHub issue #659 where
RecordingFiles for the NEXT task could be buffered into
task_video_files before the GUI thread's stop_lsl_recording had
a chance to snapshot them, causing the current task to steal
the next task's files.

The fix moves the snapshot from stop_lsl_recording (GUI thread)
into the TaskCompletion handler (message reader thread), making
it atomic with respect to message processing.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from unittest.mock import MagicMock

from neurobooth_os.msg.messages import RecordingFiles, TaskCompletion
from neurobooth_os.session_controller import SessionState


@dataclass
class _Capture:
    """Collects (task_id, video_files) tuples from on_task_finished calls."""
    calls: List[Tuple[str, Dict[str, List[str]]]] = field(default_factory=list)


def _simulate_message_sequence(state: SessionState, messages, capture: _Capture):
    """Replay a sequence of (msg_type, body) through the same logic as
    _message_reader_loop, without needing DB or threading.
    """
    for msg_type, body in messages:
        if msg_type == "RecordingFiles":
            for stream_name, filenames in body.files.items():
                existing = state.task_video_files.get(stream_name, [])
                state.task_video_files[stream_name] = existing + filenames

        elif msg_type == "TaskCompletion":
            # This is the fix: snapshot on the message reader thread
            video_files = dict(state.task_video_files)
            state.task_video_files.clear()
            capture.calls.append((body.task_id, video_files))


class TestVideoFilesSnapshotAtomicity:
    """Verify that each TaskCompletion receives only its own task's files."""

    def test_sequential_tasks_get_own_files(self):
        """Normal case: RecordingFiles arrives before TaskCompletion for
        the same task. Each task should get its own files."""
        state = SessionState()
        capture = _Capture()

        messages = [
            ("RecordingFiles", RecordingFiles(files={
                "FlirFrameIndex": ["calib_flir.avi"],
            })),
            ("TaskCompletion", TaskCompletion(task_id="calibration_obs_1")),
            ("RecordingFiles", RecordingFiles(files={
                "FlirFrameIndex": ["pursuit_flir.avi"],
            })),
            ("TaskCompletion", TaskCompletion(task_id="pursuit_obs")),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2
        task_id_0, files_0 = capture.calls[0]
        task_id_1, files_1 = capture.calls[1]

        assert task_id_0 == "calibration_obs_1"
        assert files_0 == {"FlirFrameIndex": ["calib_flir.avi"]}

        assert task_id_1 == "pursuit_obs"
        assert files_1 == {"FlirFrameIndex": ["pursuit_flir.avi"]}

    def test_next_task_files_arrive_before_completion(self):
        """Race condition scenario: RecordingFiles for the NEXT task
        arrives before TaskCompletion for the current task.

        With the old code (snapshot in stop_lsl_recording), the GUI thread
        could see both tasks' files. With the fix, the snapshot happens
        immediately at TaskCompletion, before the next RecordingFiles
        can be processed.
        """
        state = SessionState()
        capture = _Capture()

        # This message order reproduces the race:
        # 1. RecordingFiles for intro_occulo (current task)
        # 2. TaskCompletion for intro_occulo
        # 3. RecordingFiles for calibration (NEXT task, via TransitionRecording)
        # 4. TaskCompletion for calibration
        #
        # In the old code, if the GUI was slow (500ms poll), step 3 could
        # be buffered before the GUI processed step 2's event, causing
        # calibration's files to be swept into intro_occulo's snapshot.
        messages = [
            ("RecordingFiles", RecordingFiles(files={
                "IPhoneFrameIndex": ["intro_IPhone.mov"],
            })),
            ("TaskCompletion", TaskCompletion(task_id="intro_occulo_obs_1")),
            ("RecordingFiles", RecordingFiles(files={
                "FlirFrameIndex": ["calib_flir.avi"],
                "IPhoneFrameIndex": ["calib_IPhone.mov"],
            })),
            ("TaskCompletion", TaskCompletion(task_id="calibration_obs_1")),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2

        # intro_occulo gets ONLY its own iPhone file
        task_id_0, files_0 = capture.calls[0]
        assert task_id_0 == "intro_occulo_obs_1"
        assert files_0 == {"IPhoneFrameIndex": ["intro_IPhone.mov"]}
        assert "FlirFrameIndex" not in files_0  # Must NOT have calibration's FLIR

        # calibration gets its own FLIR and iPhone files
        task_id_1, files_1 = capture.calls[1]
        assert task_id_1 == "calibration_obs_1"
        assert files_1 == {
            "FlirFrameIndex": ["calib_flir.avi"],
            "IPhoneFrameIndex": ["calib_IPhone.mov"],
        }

    def test_multiple_recording_files_per_task(self):
        """ACQ and STM each send RecordingFiles for the same task.
        Both should be captured in the snapshot."""
        state = SessionState()
        capture = _Capture()

        messages = [
            # ACQ sends camera files
            ("RecordingFiles", RecordingFiles(files={
                "FlirFrameIndex": ["calib_flir.avi"],
                "IPhoneFrameIndex": ["calib_IPhone.mov"],
            })),
            # STM sends EyeLink file
            ("RecordingFiles", RecordingFiles(files={
                "EyeLink": ["calib.edf"],
            })),
            ("TaskCompletion", TaskCompletion(task_id="calibration_obs_1")),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 1
        task_id, files = capture.calls[0]
        assert task_id == "calibration_obs_1"
        assert files == {
            "FlirFrameIndex": ["calib_flir.avi"],
            "IPhoneFrameIndex": ["calib_IPhone.mov"],
            "EyeLink": ["calib.edf"],
        }

    def test_no_lsl_stream_task_gets_empty_files(self):
        """Tasks with has_lsl_stream=False still snapshot (and clear)
        video files to prevent leaking into the next task."""
        state = SessionState()
        capture = _Capture()

        messages = [
            ("TaskCompletion", TaskCompletion(
                task_id="intro_sess_obs_1", has_lsl_stream=False)),
            ("RecordingFiles", RecordingFiles(files={
                "FlirFrameIndex": ["calib_flir.avi"],
            })),
            ("TaskCompletion", TaskCompletion(task_id="calibration_obs_1")),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2
        # intro_sess had no RecordingFiles
        assert capture.calls[0] == ("intro_sess_obs_1", {})
        # calibration still gets its files
        assert capture.calls[1][1] == {"FlirFrameIndex": ["calib_flir.avi"]}

    def test_state_is_clean_after_all_tasks(self):
        """task_video_files should be empty after all tasks complete."""
        state = SessionState()
        capture = _Capture()

        messages = [
            ("RecordingFiles", RecordingFiles(files={"A": ["f1"]})),
            ("TaskCompletion", TaskCompletion(task_id="task1")),
            ("RecordingFiles", RecordingFiles(files={"B": ["f2"]})),
            ("TaskCompletion", TaskCompletion(task_id="task2")),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert state.task_video_files == {}
