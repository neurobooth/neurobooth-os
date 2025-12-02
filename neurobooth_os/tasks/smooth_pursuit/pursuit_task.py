# -*- coding: utf-8 -*-
import numpy as np
from math import sin, pi
from psychopy import core
import pylink
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix, peak_vel2freq, deg2rad
from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC


class Pursuit(Eyelink_HostPC):
    def __init__(
        self,
        **kwargs,
    ):

        super().__init__(**kwargs)
        self.amplitude_deg = kwargs["amplitude_deg"]
        self.peak_velocity_deg = kwargs["peak_velocity_deg"]
        self.amplitude_pixel = deg2pix(
            self.amplitude_deg, self.subj_screendist_cm, self.pixpercm
        )
        self.angular_freq = peak_vel2freq(
            self.peak_velocity_deg, self.peak_velocity_deg
        )
        self.ntrials = kwargs["ntrials"]
        self.mov_pars = [
            self.amplitude_pixel,
            0,
            deg2rad(kwargs["start_phase_deg"]),
            0,
            self.angular_freq,
            self.angular_freq,
        ]

    def present_stimulus(self, duration=0, **kwargs):
        self.run_trial(self.mov_pars)

    def run_trial(self, movement_pars):
        """Run a smooth pursuit trial

        trial_duration: the duration of the pursuit movement
        movement_pars: [amp_x, amp_y, phase_x, phase_y, freq_x, freq_y]
        The following equation defines a sinusoidal movement pattern
        y(t) = amplitude * sin(2 * pi * frequency * t + phase)
        for circular or elliptic movements, the phase in x and y directions
        should be pi/2 (direction matters)."""

        # Parse the movement pattern parameters
        amp_x, amp_y, phase_x, phase_y, freq_x, freq_y = movement_pars

        # Send a message to mark movement onset
        self.sendMessage(self.marker_task_start)

        # Drift check/correction, params, x, y, draw_target, allow_setup
        tar_x = amp_x * sin(phase_x)
        tar_y = amp_y * sin(phase_y)
        self.target.pos = (tar_x, tar_y)
        self.target.draw()
        self.win.flip()
        self.update_screen(tar_x, tar_y)
        self.send_target_loc(self.target.pos)

        frame = 0
        time_array = []
        while True:
            self.target.pos = (tar_x, tar_y)
            self.target.draw()
            self.win.flip()
            self.update_screen(tar_x, tar_y)
            self.send_target_loc(self.target.pos)

            flip_time = core.getTime()
            frame += 1
            if frame == 1:
                self.sendMessage("Movement onset")
                move_start = core.getTime()

            time_elapsed = flip_time - move_start
            time_array.append(flip_time)

            # update the target position
            tar_x = amp_x * sin(2 * pi * freq_x * time_elapsed + phase_x)
            tar_y = amp_y * sin(2 * pi * freq_y * time_elapsed + phase_y)

            # break if the time elapsed exceeds the trial duration
            if time_elapsed > self.ntrials * (1 / freq_x):
                time_array = np.array(time_array)
                time_array = np.diff(time_array)
                break

            if self.abort_keys is not None and self.abort_keys:
                if self.get_abort_key(self.abort_keys):
                    self.quit_stimulus = True
                    break

        self.time_array = time_array
        # clear the window
        self.win.color = (0, 0, 0)
        self.win.flip()
        self.clear_screen()

        # Stop recording
        self.setOfflineMode()

        self.sendMessage(self.marker_task_end)

        # Send trial variables to record in the EDF data file
        self.sendMessage(f"!V TRIAL_VAR amp_x {amp_x:.2f}")
        self.sendMessage(f"!V TRIAL_VAR amp_y {amp_y:.2f}")
        self.sendMessage(f"!V TRIAL_VAR phase_x {phase_x:.2f}")
        pylink.pumpDelay(1)  # give the tracker a break
        self.sendMessage(f"!V TRIAL_VAR phase_y {phase_y:.2f}")
        self.sendMessage(f"!V TRIAL_VAR freq_x {freq_x:.2f}")
        self.sendMessage(f"!V TRIAL_VAR freq_y {freq_y:.2f}")
        self.sendMessage(f"!V TRIAL_VAR ntrials {self.ntrials:.2f}")

        # Send a 'TRIAL_RESULT' message to mark the end of the trial
        self.sendMessage("TRIAL_RESULT")

        # TODO: Should this go before the message sending above?
        if self.quit_stimulus:
            return


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from neurobooth_os import config
    config.load_config()

    task = Pursuit(
        amplitude_deg=30,
        peak_velocity_deg=30,
        start_phase_deg=0,
        ntrials=5,
        )
    task.run(show_continue_repeat_slide=True)

    tstmp = task.time_array
    plt.figure()
    plt.hist(tstmp, 15)
    plt.figure()
    plt.plot(tstmp)
