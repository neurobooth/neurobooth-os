from neurobooth_os.tasks.task_instruction import InstructionTask


class Introduction_Task(InstructionTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_complete(self):
        pass

    def present_repeat_task_option(self, show_continue_repeat_slide: bool) -> bool:
        pass

    def present_repeat_instruction_option(self, show_continue_repeat_slide: bool = False):
        super().present_repeat_instruction_option(show_continue_repeat_slide=False)
