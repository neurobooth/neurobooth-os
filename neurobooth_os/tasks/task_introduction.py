from neurobooth_os.tasks.task_instruction import InstructionTask


class Introduction_Task(InstructionTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_complete(self):
        pass

    def present_instructions(self, show_continue_repeat_slide: bool = False):
        super().present_instructions(show_continue_repeat_slide=False)
