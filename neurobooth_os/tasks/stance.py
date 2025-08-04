from neurobooth_os.tasks.task import Task
from neurobooth_os.tasks import utils
from psychopy import sound, event
from pylsl import local_clock


class Stance(Task):
    """
        Common methods for Stance tasks
    """
    
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def play_tone(self, freq = 1000, tone_duration = 0.2):
        """
            Plays a tone at 1000 hz, for 0.2 s, in two channel stereo mode
        """
        tone = sound.Sound(freq, tone_duration, stereo=True)
        tone.play()
        utils.countdown(tone_duration + 0.02) # wait for 20 ms longer so tone can play fully
    

    def update_screen_color_to_white(self):
        # change screen color from grey to white and flip to update the screen
        white = (1, 1, 1)
        self.win.color = white
        self.win.flip()


    def update_trial_screen(self, text):
        """
            Creates a trial screen and displays it on monitor
            Wrapper around utils.create_text_screen
        """
        # since trial window is assumed to be white, text color is set to black 
        trial_screen = utils.create_text_screen(self.win, text, 'black')
        trial_screen.draw()
        self.win.flip()


    def delay(self, period: float) -> None:
        """
            Function to stall a loop for user defined time
            specified by 'period' in seconds
        """
        t1 = local_clock()
        t2 = t1
        while t2 - t1 < period:
            t2 = local_clock()


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
        self.win.color = (0, 0, 0)
        self.win.flip()

        trial_end_text = f"Trial {trial_number} ended\n\nTime Elapsed = {trial_time} s\n\nPress CONTINUE to proceed"
        trial_end_screen = utils.create_text_screen(self.win, trial_end_text)
        utils.present(self.win, trial_end_screen, waitKeys=True)


class Sitting(Stance):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def present_task(
        self,
        prompt=True,
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
            self.perform_sitting_trial(duration, wait_keys, trial_text)
            self.present_trial_ended_msg(trial_number=nth+1, trial_time=duration)

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


    def perform_sitting_trial(self, duration: int, wait_keys: bool, trial_text: str):
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
        self.play_tone()


class Standing(Stance):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def present_task(
        self,
        prompt=True,
        duration=0,
        wait_keys=True,
        trial_intruct=["Standing Trial 1", "Standing Trial 2"],
        trial_text='Press CONTINUE to end trial',
        screen_update_interval = 1,
        **kwargs
    ):
        self.send_marker(self.marker_task_start)

        for nth, trl in enumerate(trial_intruct):
            self.display_trial_instructions(trl)
            self.countdown_to_stimulus()
            trial_time = self.perform_standing_trial(duration, wait_keys, trial_text, screen_update_interval)
            self.present_trial_ended_msg(trial_number=nth+1, trial_time=round(trial_time))

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

    
    def perform_standing_trial(self, duration: int, wait_keys: bool, trial_text: str, screen_update_interval: int) -> float:
        """
            Standing trial
            This trial tracks the time that has elapsed since starting and:
            1. Plays tone when certain amount of time has passed
            2. Updates screen at fixed intervals
            3. Looks for a key press to end trial
        """

        # wait_keys must be True for standing trial to work
        assert wait_keys, ':param wait_keys: must be True'

        self.update_screen_color_to_white()

        # send trial start marker
        self.send_marker(f"Trial_start", True)

        # display trial screen
        self.update_trial_screen(trial_text)

        fail_safe_duration = duration + duration
        trial_time_elapsed = 0
        screen_last_updated = 0
        tone_played = False
        event.clearEvents(eventType='keyboard')
        #start trial timer loop
        while True:

            # delay loop for 10 ms
            self.delay(0.01)

            # update time_elapsed
            trial_time_elapsed = trial_time_elapsed + 0.01

            # update screen at fixed intervals
            if trial_time_elapsed - screen_last_updated > screen_update_interval:
                self.update_trial_screen(trial_text + f"\n\nTime elapsed = {round(trial_time_elapsed)} s")
                screen_last_updated = trial_time_elapsed

            # play tone at duration seconds
            if trial_time_elapsed > duration and not tone_played:
                self.play_tone(1500, 0.5)
                tone_played = True

            # check for key press
            press = event.getKeys()
            if any([k in self.advance_keys for k in press]):
                self.update_trial_screen(trial_text + f"\n\nTime elapsed = {round(trial_time_elapsed)} s")
                self.play_tone()
                self.send_marker(f"Trial_end", True)
                return trial_time_elapsed

            # final fail safe to prevent infinite loop
            if trial_time_elapsed > fail_safe_duration:
                self.update_trial_screen(trial_text + f"\n\nNo Response: Ended trial at {fail_safe_duration} s")
                self.play_tone(1000, 2)
                self.send_marker(f"Trial_end", True)
                return trial_time_elapsed


if __name__ == "__main__":
    t = Standing()
    t.run(duration=5)
