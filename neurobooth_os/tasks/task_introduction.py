from neurobooth_os.tasks import BasicTask


class Introduction_Task(BasicTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def run(self, **kwargs):
        self.present_instructions(prompt=False)
