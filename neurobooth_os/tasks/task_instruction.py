from neurobooth_os.tasks.task_basic import BasicTask


class InstructionTask(BasicTask):
    """
    A basic task that includes presenting instructions by default

    It also includes present_complete through inheritance from BasicTask
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_repeat_task_option(self, show_continue_repeat_slide: bool) -> bool:
        """
        Don't offer to repeat instructions
        """
        pass

    def present_instructions(self):
        """
        Present instructions before stimulus.
        """
        self._load_instruction_video()
        self._show_video(video=self.instruction_video, msg="Intructions")
