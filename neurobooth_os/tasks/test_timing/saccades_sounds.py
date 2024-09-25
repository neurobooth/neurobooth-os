# -*- coding: utf-8 -*-
from psychopy import prefs

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

from pylsl import local_clock
from psychopy import sound

from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix
from neurobooth_os.tasks.task import Task_Eyetracker


def countdown(period):
    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        t2 = local_clock()


class Saccade_synch(Task_Eyetracker):
    def __init__(
            self,
            wait_center: float,
            target_size: float,
            num_iterations: int,
            monochrome: bool,
            tone_freq: int,
            tone_duration: float,
            **kwargs
    ):

        super().__init__(**kwargs)
        self.n_trials = int(num_iterations)
        self.wait_center = wait_center
        self.pointer_size_deg = target_size
        self.pointer_size_pixel = deg2pix(
            self.pointer_size_deg, self.subj_screendist_cm, self.pixpercm
        )

        self.tone_freq = tone_freq
        self.tone_duration = tone_duration

        if monochrome:
            self.color_sequence = ["black", "white", "black", "white"]
        else:
            self.color_sequence = ["green", "red", "green", "blue"]

        self.target_positions = [(0, 0), (-480, 0), (0, 0), (480, 0)]

    def run(self, prompt=True, last_task=False, **kwarg):
        self.present_instructions(prompt)
        self.run_trials(prompt)
        # self.present_complete(last_task)
        return self.events

    def run_trials(self, prompt=True):
        """Run an altered saccades task that changes the screen color and plays a tone at every transition."""
        self.target.size = self.pointer_size_pixel
        self.target.pos = self.target_positions[-1]
        self.win.color = self.color_sequence[-1]
        self.win.flip()

        # Send a message to mark movement onset
        self.sendMessage(self.marker_task_start)
        for _ in range(self.n_trials):
            for tgt_pos, color in zip(self.target_positions, self.color_sequence):
                self.win.color = color
                self.target.pos = tgt_pos
                self.target.draw()
                tone = sound.Sound(self.tone_freq, self.tone_duration, stereo=True)
                tone.play(when=self.win.getFutureFlipTime(clock="ptb"))
                self.win.flip()
                self.sendMessage(self.marker_trial_start)
                self.send_target_loc(self.target.pos)

                countdown(self.wait_center)

        # clear the window
        self.win.color = (0, 0, 0)
        self.win.flip()

        # Stop recording
        self.setOfflineMode()

        self.sendMessage(self.marker_task_end)

        if prompt:
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.run_trials,
                waitKeys=False,
            )


def test_script() -> None:
    from neurobooth_os.iout.metadator import read_stimuli
    kwargs = read_stimuli()['timing_test_task_1'].model_dump()
    task = Saccade_synch(**kwargs)
    task.run(prompt=False)


if __name__ == "__main__":
    test_script()
