from neurobooth_os.tasks.task_basic import BasicTask


class Introduction_Task(BasicTask):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_complete(self):
        pass

    def present_instructions(self):
        """
        Present instructions before stimulus.
        """
        self._load_instruction_video()
        self._show_video(video=self.instruction_video, msg="Intructions")

    def present_repeat_instruction_option(self, show_continue_repeat_slide: bool = False):
        super().present_repeat_instruction_option(show_continue_repeat_slide=False)
