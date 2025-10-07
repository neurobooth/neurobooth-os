from neurobooth_os.tasks import Task


class Introduction_Task(Task):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self, **kwargs):
        self.present_instructions(prompt=False)
