from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks import utils
from psychopy import sound
from pylsl import local_clock

class Stance(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def play_tone(self):
        tone = sound.Sound(1000, 0.2, stereo=True)
        tone.play()
    
    def timer(self, elapsed_time:int = 0, time_period: int = 1):
        # start timer 
        t1 = local_clock()
        t2 = t1
        while t2 - t1 < time_period:
            t2 = local_clock()
        # timer ends -> update elapsed time
        return elapsed_time + time_period
        

    
    def present_task(
        self,
        prompt=True,
        duration=0,
        wait_keys=True,
        trial_intruct=["trial 1", "trial 2"],
        trial_text='Press any key to end trial',
        use_timer=False,
        **kwargs
    ):

        self.send_marker(self.marker_task_start)

        for nth, trl in enumerate(trial_intruct):
            self.display_trial_instructions(trl)
            self.countdown_to_stimulus()
            trial_time = self.perform_trial(duration, wait_keys, trial_text, use_timer)
            self.present_trial_ended_msg(trial_number=nth+1, trial_time=trial_time)

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

    def perform_trial(self, duration: int, wait_keys: bool, trial_text: str, use_timer: bool):
        # change screen color from grey to white and flip to update the screen
        white = (1, 1, 1)
        self.win.color = white
        self.win.flip()

        if use_timer: # Timed trials that end with key press - Stance tasks
            pass
        elif duration and wait_keys==False: # Show trial screen for set duration and end - Sitting task
            self.show_text(
                screen=utils.create_text_screen(win=self.win, text=trial_text, text_color="black"),
                msg="Trial",
                wait_time=duration,
                waitKeys=wait_keys,
                abort_keys=None, # Stance trials cannot be aborted
            )
            return duration
        elif duration==0 and wait_keys: # Trial with unlimited duration which ends with key press - Tandem Walk
            self.show_text(
                screen=utils.create_text_screen(win=self.win, text=trial_text, text_color="black"),
                msg="Trial",
                wait_time=duration,
                waitKeys=wait_keys,
                abort_keys=None, # Stance trials cannot be aborted
            )
            return duration
            
        

    def present_trial_ended_msg(self, trial_number: int, trial_time: int):
        trial_end_text = f"Trial {trial_number} ended\n\nTime Elapsed = {trial_time}\n\nPress CONTINUE to proceed"
        trial_end_screen = utils.create_text_screen(self.win, trial_end_text)
        utils.present(self.win, trial_end_screen, waitKeys=True, abort_keys=self.abort_keys)


    def display_trial_instructions(self, trl_instructions) -> None:
        """
        Display the instructions for the current trial
        Parameters
        ----------
        trl_instructions str: The instructions for the current trial
        """
        msg = utils.create_text_screen(self.win, trl_instructions + "\n\nPress CONTINUE to start trial")
        utils.present(self.win, msg)


if __name__ == "__main__":
    from neurobooth_os import config
    config.load_config()
    t = Stance()
    t.run()
