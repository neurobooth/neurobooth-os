"""
The MOT task is composed of a sequence of "frames".
This module handles task-level aspects and organization, such as:
   1. Task parameters
   2. Which frames should be presented
   3. The order of frame presentation
   4. Early stopping criteria based on performance
   5. Saving performance reports
"""

# TODO: Update CSV files with one-time v2 updator script as described in Slack/shortcut

import os.path as op
from typing import List
from itertools import chain
import pandas as pd
from psychopy import visual

import neurobooth_os
from neurobooth_os.tasks.task import TaskAborted
from neurobooth_os.tasks import Task_Eyetracker
from neurobooth_os.tasks.MOT.frame import (
    MOTFrame,
    ImageFrame,
    TrialResult,
    TrialFrame,
    PracticeFrame,
    ExampleFrame,
    FrameParameters,
    TrialFrameParameters,
    ImageFrameParameters,
    FrameChunk,
)
from neurobooth_os.iout.stim_param_reader import EyeTrackerStimArgs, get_cfg_path


class MotStimArgs(EyeTrackerStimArgs):
    continue_message: str
    chunk_timeout_sec: float
    practice_chunks: List[FrameChunk]
    test_chunks: List[FrameChunk]


class MOTException(Exception):
    pass


class MOT(Task_Eyetracker):
    root_dir = op.join(neurobooth_os.__path__[0], 'tasks', 'MOT')

    def __init__(
        self,
        path: str,
        subj_id: str,
        task_name: str = 'MOT',
        continue_message: str = 'continue.png',
        chunk_timeout_sec: float = 120,
        practice_chunks: List[FrameChunk] = (),
        test_chunks: List[FrameChunk] = (),
        **kwargs,
    ):
        """
        :param path: Output path for the task results.
        :param subj_id: The subject ID.
        :param task_name: The name of this task.
        :param continue_message: Asset path to the image to display for the task continue message.
        :param chunk_timeout_sec: How long it takes to "time out" on a chunk and trigger the early stop criterion.
        :param practice_chunks: A series of frame chunk configurations defining the task practice.
        :param test_chunks: A series of frame chunk configurations defining the testing portion of the test.
        """
        super().__init__(**kwargs)

        self.output_path = path
        self.task_name = task_name
        self.subject_id = subj_id

        self.win.color = "white"
        self.win.flip()

        self.score: int = 0
        self.n_repetitions: int = 0
        self.chunk_timeout_sec: float = chunk_timeout_sec
        # Stim params are saved in case we need to recreate frames to flush old data during task reinit
        self.stimulus_params = [continue_message, practice_chunks, test_chunks]
        self._init_frame_sequence(*self.stimulus_params)

    @classmethod
    def asset_path(cls, asset: str) -> str:
        """
        Get the path to the specified asset.
        :param asset: The name of the asset/file.
        :return: The file system path to the asset.
        """
        return op.join(cls.root_dir, 'assets', asset)

    @staticmethod
    def animation_path(animation_file: str) -> str:
        """
        Get the path to the specified animation file.
        :param animation_file: The name of the animation file (extension included).
        :return: The path to the file in the config folder.
        """
        return op.join(get_cfg_path('assets'), 'mot_animations', animation_file)

    def _create_frame(self, params: FrameParameters) -> MOTFrame:
        if isinstance(params, TrialFrameParameters):
            params: TrialFrameParameters
            if params.trial_type == 'test':
                self.trial_count += 1
                return TrialFrame(self.win, self, self.trial_count, params)
            elif params.trial_type == 'practice':
                return PracticeFrame(self.win, self, 0, params)
            elif params.trial_type == 'example':
                return ExampleFrame(self.win, self, 0, params)
            else:
                raise MOTException(f'Unrecognized trial type: {params.trial_type}')
        elif isinstance(params, ImageFrameParameters):
            params: ImageFrameParameters
            return ImageFrame(self.win, self, params.image_path)
        else:
            raise MOTException(f'Unexpected frame parameter type: {type(params)}')

    def _create_chunk(self, chunk: FrameChunk) -> List[MOTFrame]:
        self.trial_count = 0  # Keep track of how many test trial frames are in a chunk
        return [self._create_frame(params) for params in chunk.frames]

    def _init_frame_sequence(
            self,
            continue_message: str,
            practice_chunks: List[FrameChunk],
            test_chunks: List[FrameChunk],
    ) -> None:
        """Create the sequences of frames that compose this task"""
        self.continue_message = visual.ImageStim(
            self.win,
            image=MOT.asset_path(continue_message),
            pos=(0, 0),
            units="deg",
        )

        self.practice_chunks = [self._create_chunk(chunk) for chunk in practice_chunks]
        self.test_chunks = [self._create_chunk(chunk) for chunk in test_chunks]

    def run(self, prompt=True, last_task=False, **kwargs):
        if self.n_repetitions > 0:
            self._init_frame_sequence(*self.stimulus_params)  # Create new frames for repeats to flush old data

        self.score = 0
        self.present_instructions(prompt)
        self.win.color = "white"
        self.win.flip()
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        try:
            for chunk in self.practice_chunks:
                self.run_chunk(chunk)
            for chunk in self.test_chunks:
                self.run_chunk(chunk)
                # Check early stopping criterion and stop if met
                total_click_duration = MOT.chunk_click_duration(chunk)
                if total_click_duration > self.chunk_timeout_sec:
                    print(f'MOT timed out: total_click_duration={total_click_duration} s')
                    break
        except TaskAborted:
            print('MOT aborted')
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True)

        self.save_results()

        if prompt:  # Check if task should be repeated
            func_kwargs_func = {"prompt": prompt}
            self.n_repetitions += 1
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.run,
                func_kwargs=func_kwargs_func,
                waitKeys=False,
            )

        self.present_complete(last_task)
        return self.events

    @staticmethod
    def run_chunk(chunk: List[MOTFrame]) -> None:
        for frame in chunk:
            frame.run()

    @staticmethod
    def chunk_click_duration(chunk: List[MOTFrame]) -> float:
        """Compute the total time spent during clicks for a chunk. Timeouts are only penalized once."""
        total_duration = 0
        for c in chunk:
            if not isinstance(c, TrialFrame):
                continue
            results = c.results()
            total_duration += results.click_duration
            if results.state == 'timeout':
                total_duration += c.click_timeout
        return total_duration

    def save_csv(self, data: pd.DataFrame, name: str) -> None:
        """
        Save a CSV file generated from the given DataFrame
        :param data: The DataFrame to save
        :param name: The type of data (e.g., outcomes, results, circle history)
        """
        repetition_str = f'_rep-{self.n_repetitions}' if self.n_repetitions > 0 else ''
        fname = f"{self.subject_id}_{self.task_name}_{name}_v2{repetition_str}.csv"
        data.to_csv(op.join(self.output_path, fname))
        self.task_files.append(fname)

    def save_results(self):
        all_frames: List[MOTFrame] = [*chain(*self.practice_chunks), *chain(*self.test_chunks)]
        results: List[TrialResult] = [
            frame.results() for frame in all_frames
            if isinstance(frame, TrialFrame) and frame.trial_type in ('test', 'practice')
        ]
        results_df = pd.DataFrame(results, columns=TrialResult._fields)

        test_results = results_df.loc[(results_df['trial_type'] == 'test') & (results_df['state'] == 'click')]
        total_targets = test_results['n_targets'].sum()
        total_hits = test_results['n_correct'].sum()
        total_click_duration = test_results['click_duration'].sum()
        outcome_df = pd.DataFrame.from_dict({
            'score': self.score,
            'pct_correct': total_hits / total_targets if total_targets > 0 else 0,
            'total_click_duration': total_click_duration,
        }, orient="index", columns=["vals"])

        self.save_csv(results_df, 'results')
        self.save_csv(outcome_df, 'outcomes')


if __name__ == "__main__":
    from psychopy import monitors

    monitor_width = 55
    monitor_distance = 60
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=monitor_distance
    )
    win = visual.Window(
        [1920, 1080], fullscr=False, monitor=customMon, units="pix", color="white"
    )

    self = MOT(win=win)
    self.run()
    win.close()
