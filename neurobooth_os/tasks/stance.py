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


    def play_tone(self):
        tone = sound.Sound(1000, 0.2, stereo=True)
        tone.play()
        utils.countdown(0.22) # wait for 220 ms so tone can play for 200 ms


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
        trial_end_text = f"Trial {trial_number} ended\n\nTime Elapsed = {trial_time}\n\nPress CONTINUE to proceed\n\nPress Q to end task"
        trial_end_screen = utils.create_text_screen(self.win, trial_end_text)
        utils.present(self.win, trial_end_screen, waitKeys=True, abort_keys=self.abort_keys)



class Sitting(Stance):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)


    def present_task(
        self,
        prompt=True,
        duration=5,
        wait_keys=False,
        trial_intruct=["Sitting Posture"],
        trial_text='Press any key to end trial',
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
        # change screen color from grey to white and flip to update the screen
        white = (1, 1, 1)
        self.win.color = white
        self.win.flip()
        
        import time
        self.show_text(
            screen=utils.create_text_screen(win=self.win, text=trial_text, text_color="black"),
            msg="Trial",
            wait_time=duration,
            waitKeys=wait_keys,
            abort_keys=None, # Stance trials cannot be aborted
        )
        self.play_tone()




    
    # def timer(self, elapsed_time:int = 0, time_period: int = 1):
    #     # start timer 
    #     t1 = local_clock()
    #     t2 = t1
    #     while t2 - t1 < time_period:
    #         t2 = local_clock()
    #     # timer ends -> update elapsed time
    #     return elapsed_time + time_period
    
    # def delay(self, period: float) -> None:
    #     '''Function to stall a loop for user defined time
    #        specified by 'period' defined in seconds
    #     '''
    #     t1 = local_clock()
    #     t2 = t1
    #     while t2 - t1 < period:
    #         t2 = local_clock()
        

    
    # def present_task(
    #     self,
    #     prompt=True,
    #     duration=0,
    #     wait_keys=True,
    #     trial_intruct=["trial 1", "trial 2"],
    #     trial_text='Press any key to end trial',
    #     use_timer=False,
    #     **kwargs
    # ):

    #     self.send_marker(self.marker_task_start)

    #     for nth, trl in enumerate(trial_intruct):
    #         self.display_trial_instructions(trl)
    #         self.countdown_to_stimulus()
    #         trial_time = self.perform_trial(duration, wait_keys, trial_text, use_timer)
    #         self.present_trial_ended_msg(trial_number=nth+1, trial_time=trial_time)

    #     self.send_marker(self.marker_task_end)

    #     if prompt:
    #         func_kwargs = locals()
    #         del func_kwargs["self"]
    #         self.show_text(
    #             screen=self.press_task_screen,
    #             msg="Task-continue-repeat",
    #             func=self.present_task,
    #             func_kwargs=func_kwargs,
    #             waitKeys=False,
    #         )

    

    # def perform_trial(self, duration: int, trial_screen_update_interval: int, wait_keys: bool):
    #     # change screen color from grey to white and flip to update the screen
    #     white = (1, 1, 1)
    #     self.win.color = white
    #     self.win.flip()

    #     # send trial start marker

    #     # show trial screen here

    #     #start trial timer loop
    #     t1 = local_clock()
    #     t2 = t1
    #     trial_time_elapsed = 0
    #     screen_last_updated = 0
    #     while trial_time_elapsed < duration+10:
            
    #         if trial_time_elapsed - screen_last_updated == trial_screen_update_interval:
    #             # update trial screen
    #             # increment screen_last_updated
    #             screen_last_updated = screen_last_updated + trial_time_elapsed
            
    #         if wait_keys:
    #             press = event.getKeys()
    #             if press == self.advance_keys:
    #                 break

    #         # stall the loop for 5 ms
    #         self.delay(0.005)




        




    
    # def perform_trial(self, duration: int, wait_keys: bool, trial_text: str, use_timer: bool):
    #     # change screen color from grey to white and flip to update the screen
    #     white = (1, 1, 1)
    #     self.win.color = white
    #     self.win.flip()

    #     if use_timer: # Timed trials that end with key press - Stance tasks
    #         pass
    #     elif duration and wait_keys==False: # Show trial screen for set duration and end - Sitting task
    #         self.show_text(
    #             screen=utils.create_text_screen(win=self.win, text=trial_text, text_color="black"),
    #             msg="Trial",
    #             wait_time=duration,
    #             waitKeys=wait_keys,
    #             abort_keys=None, # Stance trials cannot be aborted
    #         )
    #         return duration
    #     elif duration==0 and wait_keys: # Trial with unlimited duration which ends with key press - Tandem Walk
    #         self.show_text(
    #             screen=utils.create_text_screen(win=self.win, text=trial_text, text_color="black"),
    #             msg="Trial",
    #             wait_time=duration,
    #             waitKeys=wait_keys,
    #             abort_keys=None, # Stance trials cannot be aborted
    #         )
    #         return duration
            
        



if __name__ == "__main__":
    t = Sitting()
    t.run(duration=0, wait_keys=True)
