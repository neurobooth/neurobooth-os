from neurobooth_os.tasks import TaskShell


class Introduction_Task(TaskShell):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self, **kwargs):
        self.present_instructions(prompt=False)
