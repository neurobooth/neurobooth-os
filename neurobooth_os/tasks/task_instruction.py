from neurobooth_os.tasks.task_basic import BasicTask


class InstructionTask(BasicTask):
    """
    A basic task that includes presenting instructions by default
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def present_instructions(self, prompt: bool = True):
        """
        Present instructions before stimulus
        Parameters
        ----------
        prompt : bool
        """
        self._load_instruction_video()
        self._show_video(video=self.instruction_video, msg="Intructions")
        if prompt:
            self.show_text(
                screen=self.instruction_end_screen,
                msg="Intructions-continue-repeat",
                func=self.present_instructions,
                waitKeys=False,
            )
