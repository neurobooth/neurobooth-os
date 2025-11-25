from neurobooth_os.tasks.task_eyetracker import Eyelink_HostPC


class Fixation_Target_Multiple(Eyelink_HostPC):
    """
    Fixation task with multiple targets. Each target is presented alone, sequentially and each is
    treated as an individual trial
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_stimulus(
        self,
        duration=3,
        trial_pos=[(0, 0), (0, 15)],
        target_size=0.7,
        **kwargs
    ):

        self.sendMessage(self.marker_task_start)

        for pos in trial_pos:
            self.target.pos = [self.deg_2_pix(pos[0]), self.deg_2_pix(pos[1])]
            self.target.size = self.deg_2_pix(target_size)  # target_size from deg to cms
            if sum(self.target.size):
                self.send_target_loc(self.target.pos)

            # Send event to eyetracker and to LSL separately
            self.sendMessage(self.marker_trial_start, False)
            self.update_screen(self.target.pos[0], self.target.pos[1])
            self.show_text(
                screen=self.target,
                msg="Trial",
                audio=None,
                wait_time=duration,
                waitKeys=False,
            )
            self.sendMessage(self.marker_trial_end, False)
            self.check_if_aborted()

        self.sendMessage(self.marker_task_end)
        self.clear_screen()


if __name__ == "__main__":

    t = Fixation_Target_Multiple()
    t.run(duration=3, trial_pos=[(0, 7.5), (15, 7.5), (-15, 0)], target_size=0.7)
