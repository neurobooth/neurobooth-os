from neurobooth_os.tasks.task_instruction import InstructionTask


class Introduction_Task(InstructionTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_instructions(self, prompt: bool = False):
        super().present_instructions(prompt=False)
