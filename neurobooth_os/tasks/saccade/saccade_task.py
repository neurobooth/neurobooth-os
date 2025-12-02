# -*- coding: utf-8 -*-
import pylink
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix
from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC
import numpy as np
from pylsl import local_clock


# def countdown(period):
#     t1 = local_clock()
#     t2 = t1
#
#     while t2 - t1 < period:
#         t2 = local_clock()


class Saccade(Eyelink_HostPC):
    def __init__(
        self,
        amplitude_deg=30,
        direction="horizontal",
        wait_center=1,
        Wait_offset=1,
        jitter_percent=0.5,
        target_size=7,
        trial_sign=[-1, -1, 1, -1, 1, -1, 1, 1, -1, -1, 1, 1],
        **kwargs,
    ):

        super().__init__(**kwargs)
        self.amplitude_deg = amplitude_deg
        self.direction = direction
        self.amplitude_pixel = deg2pix(
            self.amplitude_deg, self.subj_screendist_cm, self.pixpercm
        )
        self.trial_sign = trial_sign
        self.ntrials = len(trial_sign)
        self.wait_center = wait_center
        self.wait_offset = Wait_offset
        self.jitter_percent = jitter_percent
        self.pointer_size_deg = target_size
        self.pointer_size_pixel = deg2pix(
            self.pointer_size_deg, self.subj_screendist_cm, self.pixpercm
        )

        if direction == "horizontal":
            self.movement_pars = [self.amplitude_pixel, 0]
        elif direction == "vertical":
            self.movement_pars = [0, self.amplitude_pixel]
        else:
            raise ValueError("Only horizontal and vertical saccade is supported")

    def present_stimulus(self, **kwargs):
        """Run a smooth pursuit trial"""

        # Parse the movement pattern parameters
        amp_x, amp_y = self.movement_pars
        tar_x = amp_x
        tar_y = amp_y

        # Send a message to mark movement onset
        self.sendMessage(self.marker_task_start)

        # Drift check/correction, params, x, y, draw_target, allow_setup

        self.target.pos = (0, 0)
        self.target.size = self.pointer_size_pixel
        self.target.draw()
        self.win.flip()
        self.update_screen(0, 0)
        self.win.color = (0, 0, 0)
        self.win.flip()

        for index in range(self.ntrials):

            self.target.pos = (0, 0)
            self.target.draw()
            self.win.flip()
            self.update_screen(0, 0)
            self.send_target_loc(self.target.pos)

            self.countdown(
                self.wait_center
                + self.jitter_percent * self.wait_center * np.random.random(1)[0],
                abort_keys=self.abort_keys
            )

            self.target.pos = (tar_x, tar_y)
            self.target.draw()
            self.win.flip()
            self.update_screen(tar_x, tar_y)
            self.send_target_loc(self.target.pos)

            # update the target position
            tar_x = self.trial_sign[index] * amp_x
            tar_y = self.trial_sign[index] * amp_y

            countdown(
                self.wait_offset
                + self.jitter_percent * self.wait_offset * np.random.random(1)[0]
            )
            if self.quit_stimulus:
                break

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
        pylink.pumpDelay(1)  # give the tracker a break
        self.sendMessage(f"!V TRIAL_VAR ntrials {self.ntrials:.2f}")

        # Send a 'TRIAL_RESULT' message to mark the end of the trial
        self.sendMessage("TRIAL_RESULT")


if __name__ == "__main__":
    from neurobooth_os import config
    config.load_config()
    task = Saccade(direction="vertical", amplitude_deg=30)
    task.run(show_continue_repeat_slide=False)
