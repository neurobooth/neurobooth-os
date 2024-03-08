"""
The MOT task is composed of a sequence of "frames".
This module handles task-level aspects and organization, such as:
   1. Task parameters
   2. Which frames should be presented
   3. The order of frame presentation
   4. Early stopping criteria based on performance
   5. Saving performance reports
"""

# TODO: Generate animation file for the example trial!
# TODO: Load new params and animation files; should probably be in .neurobooth_os by configs
# TODO: Finish refactoring of parameter structures
# TODO: Update configs to point to new Task object path and to define the task parameters
# TODO: Change circle colors to be more color blind friendly
# TODO: Implement early task end logic
# TODO: Update CSV files with one-time v2 updator script as described in Slack/shortcut

import os.path as op
from typing import List
import pandas as pd
from psychopy import visual
from itertools import chain

import neurobooth_os
from neurobooth_os.tasks import Task_Eyetracker
from neurobooth_os.tasks.MOT.frame import (
    TaskAborted,
    MOTFrame,
    ImageFrame,
    TrialResult,
    TrialFrame,
    ExampleFrame,
    PracticeFrame,
    FrameChunk,
)
from neurobooth_os.iout.stim_param_reader import EyeTrackerStimArgs


# TODO: For review: keep here or move to stim_param_reader?
class MotStimArgs(EyeTrackerStimArgs):
    continue_message: str
    practice_chunks: List[FrameChunk]
    test_chunks: List[FrameChunk]


class MOT(Task_Eyetracker):
    root_dir = op.join(neurobooth_os.__path__[0], 'tasks', 'MOT')

    def __init__(
        self,
        path: str = "",
        subj_id: str = "test",
        task_name: str = "MOT",
        numCircles: int = 10,
        time_presentation: float = 3,
        trial_duration: float = 5,
        clickTimeout: float = 60,
        seed: int = 2,
        **kwargs,
    ):
        """
        :param path: Output path for the task results.
        :param subj_id: The subject ID.
        :param task_name: The name of this task.
        :param numCircles: The total number of circles to draw.
        :param time_presentation: How long the targets flash black and green.
        :param trial_duration: How long the circles move fot.
        :param clickTimeout: How long to wait for all clicks to be completed before timing out.
        :param seed: Seed used to initialize the random number sequence controlling all test trials.
        """
        super().__init__(**kwargs)

        self.output_path = path
        self.task_name = task_name
        self.subject_id = subj_id

        self.n_circles = numCircles
        self.move_duration = trial_duration
        self.flash_duration = time_presentation
        self.click_timeout = clickTimeout
        self.seed = seed
        self.paper_size = 500  # size of stimulus graphics page

        self.win.color = "white"
        self.win.flip()

        self.score: int = 0
        self.n_repetitions: int = 0
        self._init_frame_sequence()

    @classmethod
    def asset_path(cls, asset: str) -> str:
        """
        Get the path to the specified asset.
        :param asset: The name of the asset/file.
        :return: The file system path to the asset.
        """
        return op.join(cls.root_dir, 'assets', asset)

    def _init_frame_sequence(self) -> None:
        """Create the sequences of frames that compose this task"""
        self.continue_message = visual.ImageStim(
            self.win,
            image=MOT.asset_path('continue.png'),
            pos=(0, 0),
            units="deg",
        )

        common_trial_kwargs = {
            'flash_duration': self.flash_duration,
            'movement_duration': self.move_duration,
            'click_timeout': self.click_timeout,
            'n_circles': self.n_circles,
            'paper_size': self.paper_size,
            'circle_radius': 15,
            'velocity_noise': 15,
        }

        self.intro_chunk: List[MOTFrame] = [
            ImageFrame(self.win, self, 'intro.png'),
            ImageFrame(self.win, self, 'inst1.png'),
            ExampleFrame(
                self.win, self,
                n_targets=2, circle_speed=0.5, trial_count=0, random_seed='example1',
                **common_trial_kwargs
            ),
            ImageFrame(self.win, 'inst2.png'),
            PracticeFrame(
                self.win, self,
                n_targets=2, circle_speed=0.5, trial_count=0, random_seed='practice1',
                **common_trial_kwargs
            ),
            ImageFrame(self.win, self, 'inst3.png'),
            PracticeFrame(
                self.win, self,
                n_targets=3, circle_speed=0.5, trial_count=0, random_seed='practice2',
                **common_trial_kwargs
            ),
        ]

        self.chunk_3tgt: List[MOTFrame] = [ImageFrame(self.win, self, 'targ3.png')]
        self.chunk_4tgt: List[MOTFrame] = [ImageFrame(self.win, self, 'targ4.png')]
        self.chunk_5tgt: List[MOTFrame] = [ImageFrame(self.win, self, 'targ5.png')]

        for i in range(6):
            speed = i + 1
            trial_count = i + 1

            seed = self.seed + i
            self.chunk_3tgt.append(TrialFrame(
                self.win, self,
                n_targets=3, circle_speed=speed, trial_count=trial_count, random_seed=seed,
                **common_trial_kwargs
            ))

            seed = self.seed + i + 10
            self.chunk_4tgt.append(TrialFrame(
                self.win, self,
                n_targets=4, circle_speed=speed, trial_count=trial_count, random_seed=seed,
                **common_trial_kwargs
            ))

            seed = self.seed + i + 20
            self.chunk_5tgt.append(TrialFrame(
                self.win, self,
                n_targets=5, circle_speed=speed, trial_count=trial_count, random_seed=seed,
                **common_trial_kwargs
            ))

    def run(self, prompt=True, last_task=False, subj_id="test", **kwargs):
        self.subject_id = subj_id
        if self.n_repetitions > 0:
            self._init_frame_sequence()  # Create new frames for repeats to flush old data

        self.score = 0
        self.present_instructions(prompt)
        self.win.color = "white"
        self.win.flip()
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        try:
            self.run_chunk(self.intro_chunk)
            self.run_chunk(self.chunk_3tgt)
            self.run_chunk(self.chunk_4tgt)
            self.run_chunk(self.chunk_5tgt)
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

    def save_csv(self, data: pd.DataFrame, name: str) -> None:
        """
        Save a CSV file generated from the given DataFrame
        :param data: The DataFrame to save
        :param name: The type of data (e.g., outcomes, results, circle history)
        """
        repetition_str = f'_rep-{self.n_repetitions}' if self.n_repetitions > 0 else ''
        fname = f"{self.subject_id}_{self.task_name}_{name}_v2{repetition_str}.csv"
        data.to_csv(self.output_path + fname)
        self.task_files.append(fname)

    def save_results(self):
        results: List[TrialResult] = [
            frame.results()
            for frame in chain(self.intro_chunk, self.chunk_3tgt, self.chunk_4tgt, self.chunk_5tgt)
            if isinstance(frame, TrialFrame) and frame.trial_type in ['test', 'practice']
        ]
        results_df = pd.DataFrame(results, columns=TrialResult._fields)

        test_results = results_df.loc[(results_df['trial_type'] == 'test') & (results_df['state'] == 'click')]
        total_targets = test_results['n_targets'].sum()
        total_hits = test_results['n_correct'].sum()
        total_click_duration = test_results['click_duration'].sum()
        outcome_df = pd.DataFrame.from_dict({
            'score': self.score,
            'pct_correct': round(total_hits / total_targets, 3),
            'total_click_duration': round(total_click_duration, 1),
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
