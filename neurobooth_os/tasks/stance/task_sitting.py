from neurobooth_os.tasks import utils
from neurobooth_os.tasks.stance.task_stance import Stance


class Sitting(Stance):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_stimulus(
        self,
        duration=5,
        wait_keys=False,
        trial_intruct=["Sitting Posture"],
        trial_text='Press Q or any key to end trial',
        **kwargs
    ):
        self.send_marker(self.marker_task_start)

        for nth, trl in enumerate(trial_intruct):
            self.display_trial_instructions(trl)
            self.countdown_to_stimulus()
            self._perform_sitting_trial(duration, wait_keys, trial_text)
            self.present_trial_ended_msg(trial_number=nth+1, trial_time=duration)

        self.send_marker(self.marker_task_end)

    def _perform_sitting_trial(self, duration: int, wait_keys: bool, trial_text: str):
        """
            Calls task.show_text to show a static screen for 'duration' seconds
        """
        self.update_screen_color_to_white()
        self.show_text(
            screen=utils.create_text_screen(win=self.win, text=trial_text, text_color="black"),
            msg="Trial",
            wait_time=duration,
            waitKeys=wait_keys,
            abort_keys=self.abort_keys,
        )
