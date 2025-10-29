from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks import utils


class Stance(Task):
    """
        Common methods for Stance tasks
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_countdown(self) -> None:
        """No countdown before present_task"""
        pass

    def update_screen_color_to_white(self):
        # change screen color from grey to white and flip to update the screen
        # wrapper around utils.change_win_color
        white = (1, 1, 1)
        utils.change_win_color(self.win, white)

    def update_trial_screen(self, text):
        """
            Creates a trial screen and displays it on monitor
            Wrapper around utils.create_text_screen
        """
        # since trial window is assumed to be white, text color is set to black 
        trial_screen = utils.create_text_screen(self.win, text, 'black')
        trial_screen.draw()
        self.win.flip()

    def display_trial_instructions(self, trl_instructions: str) -> None:
        """
            Shows text during a trial - intended as instruction to participant
        """
        trial_start_screen = utils.create_text_screen(self.win, trl_instructions + "\n\nPress CONTINUE to start trial")
        utils.present(self.win, trial_start_screen)

    def present_trial_ended_msg(self, trial_number: int, trial_time:int) -> None:
        """
            Shows results text at end of trial
            Waits for key press before continuing
            Can press Q to end task
        """
        # change screen color back to grey
        utils.change_win_color(self.win, (0, 0, 0))

        trial_end_text = f"Trial {trial_number} ended\n\nTime Elapsed = {trial_time} s\n\nPress CONTINUE to proceed"
        trial_end_screen = utils.create_text_screen(self.win, trial_end_text)
        trial_end_screen.draw()
        self.win.flip()
        key_press = utils.get_keys(self.abort_keys + self.advance_keys)
        return key_press
