from neurobooth_os.tasks import Task



class Task_Eyetracker(Task):
    def __init__(self, eyetracker=None, **kwargs):
        super().__init__(**kwargs)

        self.eytracker = eyetracker

    def sendMessage(msg):
        pass

    def sendCommand(msg):
        pass

    def gaze_contingency():
        # move task 
        pass


class Task_Dynamic_Stim(Task_Eyetracker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run():
        # marker for each trial number
        pass



