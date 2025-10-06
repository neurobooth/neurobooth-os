from neurobooth_os.tasks import Task_Eyetracker, utils


class Task_sidetrials(Task_Eyetracker):
    """
    Tasks with two trials, one for each 'side', dominant or not dominant. It supports fixation tasks with side-trials,
    such as finger-nose
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(
        self,
        prompt=True,
        duration=3,
        target_pos=(-10, 10),
        target_size=0.7,
        trial_intruct=["trial 1", "trial 2"],
        **kwargs
    ):

        self.sendMessage(self.marker_task_start)

        for nth, trl in enumerate(trial_intruct):
            self.display_trial_instructions(trl)
            self.countdown_to_stimulus()
            self.perform_trial(duration, target_pos, target_size)
            self.present_trial_ended_msg()

        self.sendMessage(self.marker_task_end)

        if prompt:
            func_kwargs = locals()
            del func_kwargs["self"]
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                func_kwargs=func_kwargs,
                waitKeys=False,
            )

    def perform_trial(self, duration, target_pos, target_size):
        self.calc_target_position_and_size(target_pos, target_size)
        # Send event to eyetracker and to LSL separately
        self.sendMessage(self.marker_trial_start, False)
        self.show_text(
            screen=self.target,
            msg="Trial",
            wait_time=duration,
            abort_keys=self.abort_keys,
            waitKeys=False
        )
        self.sendMessage(self.marker_trial_end, False)

    def present_trial_ended_msg(self):
        msg = utils.create_text_screen(self.win, "Task on one side ended")
        utils.present(self.win, msg, wait_time=2, waitKeys=False)

    def calc_target_position_and_size(self, target_pos, target_size):
        self.target.pos = [
            self.deg_2_pix(target_pos[0]),
            self.deg_2_pix(target_pos[1]),
        ]
        self.target.size = self.deg_2_pix(
            target_size
        )  # target_size from deg to cms
        if sum(self.target.size):
            self.send_target_loc(self.target.pos)

    def display_trial_instructions(self, trl_instructions) -> None:
        """
        Display the instructions for the current trial
        Parameters
        ----------
        trl_instructions str: The instructions for the current trial
        """
        msg = utils.create_text_screen(self.win, trl_instructions + "\n\n\nPress CONTINUE")
        utils.present(self.win, msg)
