from typing import List, Optional
from random import randint, Random
import numpy as np
from psychopy import event, clock
from neurobooth_os.tasks.task import Eyelink_HostPC, TaskAborted


class SDMT(Eyelink_HostPC):
    def __init__(
            self,
            n_trials: int,
            symbols: List[str],
            seed: Optional[int],
            text_height: float,
            grid: (int, int),
            mouse_visible: bool,
            interline_gap: float,
            units: str,
            **kwargs
    ):
        """
        :param n_trials: The number of trials, where each trial presents a new random grid of test symbols
        :param symbols: The symbols to be displayed in the key (in order of presentation)
        :param seed: If provided, controls the "random" sequence of generated test symbols
        :param text_height: The height of the text
        :param grid: Specifies the number of rows and columns in the test symbol grid
        :param mouse_visible: Whether the mouse should be visible during the task
        :param interline_gap: How much space to add between each row of test symbols
        :param units: The units of the above parameters (passed through to PsychoPy)
        :param kwargs: Passthrough arguments
        """
        super().__init__(**kwargs)

        self.n_trials: int = n_trials
        self.symbols = np.array(symbols, dtype='U1')

        # Visual Parameters
        self.text_height: float = text_height
        self.grid: (int, int) = grid
        self.interline_gap: float = interline_gap
        self.units: str = units
        self.mouse_visible: bool = mouse_visible

        # Sequence Parameters
        self.seed: int = seed if (seed is not None) else randint(0, 1<<20)
        self.rng = Random(self.seed)
        self.test_sequence: np.ndarray = np.array([])

    def generate_test_sequence(self) -> np.ndarray:
        h, w = self.grid
        seq = np.full(h*w, ' ', dtype='U1')
        seq[0] = self.rng.choice(self.symbols)
        for i in range(h*w-1):
            seq[i+1] = self.rng.choice(np.setdiff1d(self.symbols, seq[i]))  # No back-to-back symbols
        return seq.reshape(self.grid)

    def draw_key(self) -> None:
        pass

    def draw_test_grid(self) -> None:
        pass

    def draw(self) -> None:
        pass

    def run_trial(self) -> None:
        self.test_sequence = self.generate_test_sequence()
        self.draw()
        self.sendMessage(self.marker_trial_start)

        event.clearEvents(eventType='keyboard')
        while not event.getKeys(self.advance_keys):
            self.check_if_aborted()
            clock.wait(0.01, hogCPUperiod=1)

        self.sendMessage(self.marker_trial_end)

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.Mouse.setVisible(self.mouse_visible)
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        try:
            for trial in range(self.n_trials):
                self.run_trial()
        except TaskAborted:
            print('SDMT aborted')
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True)

        if prompt:
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.present_task,
                waitKeys=False,
            )
