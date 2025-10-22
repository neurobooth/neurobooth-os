from neurobooth_os.tasks import InstructionTask


class Introduction_Task(InstructionTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_instructions(self, **kwargs):
        super().present_instructions(prompt=False)
