from neurobooth_os.tasks.task_basic import BasicTask


class InstructionTask(BasicTask):
    """
    A basic task that includes presenting instructions by default

    It also includes present_complete through inheritance from BasicTask
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_instructions(self, show_continue_repeat_slide: bool = True):
        """
        Present instructions before stimulus
        Parameters
        ----------
        show_continue_repeat_slide : bool   if true, show the subject a slide offering the option to repeat the
        instructions.
        """
        self._load_instruction_video()
        self._show_video(video=self.instruction_video, msg="Intructions")
        if show_continue_repeat_slide:
            self.show_text(
                screen=self.instruction_end_screen,
                msg="Intructions-continue-repeat",
                func=self.present_instructions,
                waitKeys=False,
            )
