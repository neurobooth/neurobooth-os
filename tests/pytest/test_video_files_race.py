"""Test that TaskCompletion snapshots video files atomically by fname.

Reproduces the race condition from GitHub issue #659 where RecordingFiles
for the NEXT task could be swept into the CURRENT task's snapshot.

The real race is in message insertion order, not thread timing:
ACQ's RecordingFiles for the next task can be inserted into the message
queue BEFORE STM's TaskCompletion for the current task, because ACQ
processes TransitionRecording faster than STM posts TaskCompletion.

The fix: both RecordingFiles and TaskCompletion carry an ``fname`` field
(``{session_name}_{tsk_start_time}_{task_id}``) that uniquely identifies
a single task run.  task_video_files is keyed by fname, so each
TaskCompletion pops only its own bucket.  Repeated runs of the same task
produce different fnames (different tsk_start_time) and therefore
different buckets.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from neurobooth_os.msg.messages import RecordingFiles, TaskCompletion
from neurobooth_os.session_controller import SessionState


@dataclass
class _Capture:
    """Collects (task_id, video_files) tuples from on_task_finished calls."""
    calls: List[Tuple[str, Dict[str, List[str]]]] = field(default_factory=list)


def _simulate_message_sequence(state: SessionState, messages, capture: _Capture):
    """Replay a sequence of (msg_type, body) through the same logic as
    SessionController._message_reader_loop, without needing DB or threading.
    """
    for msg_type, body in messages:
        if msg_type == "RecordingFiles":
            task_bucket = state.task_video_files.setdefault(body.fname, {})
            for stream_name, filenames in body.files.items():
                existing = task_bucket.get(stream_name, [])
                task_bucket[stream_name] = existing + filenames

        elif msg_type == "TaskCompletion":
            run_fname = getattr(body, "fname", None)
            if run_fname is not None:
                video_files = state.task_video_files.pop(run_fname, {})
            else:
                video_files = {}
            capture.calls.append((body.task_id, video_files))


class TestVideoFilesSnapshotAtomicity:
    """Verify that each TaskCompletion receives only its own task run's files."""

    def test_sequential_tasks_get_own_files(self):
        """Normal case: RecordingFiles arrives before TaskCompletion for
        the same task. Each task should get its own files."""
        state = SessionState()
        capture = _Capture()

        messages = [
            ("RecordingFiles", RecordingFiles(
                fname="100001_2026-04-10_09h-00m-00s_calibration_obs_1",
                files={"FlirFrameIndex": ["calib_flir.avi"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="calibration_obs_1",
                fname="100001_2026-04-10_09h-00m-00s_calibration_obs_1")),
            ("RecordingFiles", RecordingFiles(
                fname="100001_2026-04-10_09h-01m-00s_pursuit_obs",
                files={"FlirFrameIndex": ["pursuit_flir.avi"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="pursuit_obs",
                fname="100001_2026-04-10_09h-01m-00s_pursuit_obs")),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2
        task_id_0, files_0 = capture.calls[0]
        task_id_1, files_1 = capture.calls[1]

        assert task_id_0 == "calibration_obs_1"
        assert files_0 == {"FlirFrameIndex": ["calib_flir.avi"]}

        assert task_id_1 == "pursuit_obs"
        assert files_1 == {"FlirFrameIndex": ["pursuit_flir.avi"]}

    def test_next_task_files_arrive_before_current_completion(self):
        """The real race: RecordingFiles for the NEXT task is inserted into
        the message queue BEFORE TaskCompletion for the CURRENT task.

        This is the exact sequence observed in session 3185 (#659 regression):
          302308  ACQ→CTR  RecordingFiles   calibration files
          302309  STM→CTR  TaskCompletion   intro_occulo_obs_1
          302316  STM→CTR  TaskCompletion   calibration_obs_1

        With fname-keyed buckets, intro_occulo's TaskCompletion only pops its
        own bucket, leaving calibration's files intact for the later
        TaskCompletion.
        """
        state = SessionState()
        capture = _Capture()

        intro_fname = "100001_2026-04-10_06h-52m-56s_intro_occulo_obs_1"
        calib_fname = "100001_2026-04-10_06h-53m-09s_calibration_obs_1"

        messages = [
            # intro_occulo's own files arrive normally
            ("RecordingFiles", RecordingFiles(
                fname=intro_fname,
                files={"IPhoneFrameIndex": ["intro_IPhone.mov", "intro_IPhone.json"]})),
            # THEN calibration's files arrive (ACQ processed TransitionRecording fast)
            ("RecordingFiles", RecordingFiles(
                fname=calib_fname,
                files={
                    "FlirFrameIndex": ["calib_flir.avi"],
                    "IPhoneFrameIndex": ["calib_IPhone.mov", "calib_IPhone.json"],
                })),
            # THEN intro_occulo's TaskCompletion arrives (STM was slower)
            ("TaskCompletion", TaskCompletion(
                task_id="intro_occulo_obs_1", fname=intro_fname)),
            # Then calibration's EyeLink RecordingFiles and TaskCompletion
            ("RecordingFiles", RecordingFiles(
                fname=calib_fname,
                files={"EyeLink": ["calib.edf"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="calibration_obs_1", fname=calib_fname)),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2

        # intro_occulo gets ONLY its own files
        task_id_0, files_0 = capture.calls[0]
        assert task_id_0 == "intro_occulo_obs_1"
        assert files_0 == {"IPhoneFrameIndex": ["intro_IPhone.mov", "intro_IPhone.json"]}
        assert "FlirFrameIndex" not in files_0

        # calibration gets ALL its files — FLIR, iPhone, AND EyeLink
        task_id_1, files_1 = capture.calls[1]
        assert task_id_1 == "calibration_obs_1"
        assert files_1 == {
            "FlirFrameIndex": ["calib_flir.avi"],
            "IPhoneFrameIndex": ["calib_IPhone.mov", "calib_IPhone.json"],
            "EyeLink": ["calib.edf"],
        }

    def test_multiple_recording_files_per_task(self):
        """ACQ and STM each send RecordingFiles for the same task run.
        Both should accumulate in the same bucket."""
        state = SessionState()
        capture = _Capture()

        calib_fname = "100001_2026-04-10_06h-53m-09s_calibration_obs_1"

        messages = [
            # ACQ sends camera files
            ("RecordingFiles", RecordingFiles(
                fname=calib_fname,
                files={
                    "FlirFrameIndex": ["calib_flir.avi"],
                    "IPhoneFrameIndex": ["calib_IPhone.mov"],
                })),
            # STM sends EyeLink file
            ("RecordingFiles", RecordingFiles(
                fname=calib_fname,
                files={"EyeLink": ["calib.edf"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="calibration_obs_1", fname=calib_fname)),
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

    def test_repeated_task_gets_separate_buckets(self):
        """A task that runs twice in the same session (e.g., recalibration
        or a restarted session) produces different fnames because
        tsk_start_time differs. Each run's files must land in the correct
        bucket and not leak into the other."""
        state = SessionState()
        capture = _Capture()

        calib1_fname = "100001_2026-04-10_06h-53m-09s_calibration_obs_1"
        calib2_fname = "100001_2026-04-10_06h-59m-42s_calibration_obs_1"

        messages = [
            ("RecordingFiles", RecordingFiles(
                fname=calib1_fname,
                files={"FlirFrameIndex": ["calib1_flir.avi"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="calibration_obs_1", fname=calib1_fname)),
            ("RecordingFiles", RecordingFiles(
                fname=calib2_fname,
                files={"FlirFrameIndex": ["calib2_flir.avi"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="calibration_obs_1", fname=calib2_fname)),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2
        # First run gets its own file
        assert capture.calls[0][1] == {"FlirFrameIndex": ["calib1_flir.avi"]}
        # Second run gets its own file — not a union with the first
        assert capture.calls[1][1] == {"FlirFrameIndex": ["calib2_flir.avi"]}

    def test_non_recording_task_completion_gets_empty_dict(self):
        """Non-recording tasks send TaskCompletion with no fname (and
        has_lsl_stream=False). Those get an empty dict; they don't
        inadvertently pop any bucket."""
        state = SessionState()
        capture = _Capture()

        calib_fname = "100001_2026-04-10_06h-53m-09s_calibration_obs_1"

        messages = [
            # A non-recording task completes with no fname
            ("TaskCompletion", TaskCompletion(
                task_id="intro_sess_obs_1", has_lsl_stream=False)),
            # Then calibration runs normally
            ("RecordingFiles", RecordingFiles(
                fname=calib_fname,
                files={"FlirFrameIndex": ["calib_flir.avi"]})),
            ("TaskCompletion", TaskCompletion(
                task_id="calibration_obs_1", fname=calib_fname)),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert len(capture.calls) == 2
        assert capture.calls[0] == ("intro_sess_obs_1", {})
        assert capture.calls[1][1] == {"FlirFrameIndex": ["calib_flir.avi"]}

    def test_state_is_clean_after_all_tasks(self):
        """task_video_files should be empty after all tasks' TaskCompletions
        have been processed."""
        state = SessionState()
        capture = _Capture()

        fname_a = "100001_2026-04-10_09h-00m-00s_task1"
        fname_b = "100001_2026-04-10_09h-01m-00s_task2"

        messages = [
            ("RecordingFiles", RecordingFiles(fname=fname_a, files={"A": ["f1"]})),
            ("TaskCompletion", TaskCompletion(task_id="task1", fname=fname_a)),
            ("RecordingFiles", RecordingFiles(fname=fname_b, files={"B": ["f2"]})),
            ("TaskCompletion", TaskCompletion(task_id="task2", fname=fname_b)),
        ]

        _simulate_message_sequence(state, messages, capture)

        assert state.task_video_files == {}
