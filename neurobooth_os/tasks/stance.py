# import os.path as op
from psychopy import visual
from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks import utils


class Stance(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_task(
        self,
        prompt=True,
        duration=0,
        trial_intruct=["trial 1", "trial 2"],
    ):

        self.send_marker(self.marker_task_start)

        for nth, trl in enumerate(trial_intruct):
            self.display_trial_instructions(trl)
            # self.countdown_to_stimulus()
            self.perform_trial()
            self.present_trial_ended_msg(trial_number=nth+1)

        self.send_marker(self.marker_task_end)

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

    def perform_trial(self):
        white = (1, 1, 1)
        self.win.color = white
        self.win.flip()
        self.show_text(
            screen=utils.create_text_screen(win=self.win, text='Press any key to end trial', text_color="black"),
            msg="Trial",
            wait_time=0,
            abort_keys=None, # self.abort_keys,
            waitKeys=True
        )
        

    def present_trial_ended_msg(self, trial_number: int):
        msg = utils.create_text_screen(self.win, f"Trial {trial_number} ended")
        utils.present(self.win, msg, wait_time=2, waitKeys=False)


    def display_trial_instructions(self, trl_instructions) -> None:
        """
        Display the instructions for the current trial
        Parameters
        ----------
        trl_instructions str: The instructions for the current trial
        """
        msg = utils.create_text_screen(self.win, trl_instructions + "\n\n\nPress CONTINUE to start trial")
        utils.present(self.win, msg)


if __name__ == "__main__":
    from neurobooth_os import config
    config.load_config()
    t = Stance()
    t.run(duration=0)
