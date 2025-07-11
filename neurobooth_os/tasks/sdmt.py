from typing import List, Optional
from random import randint, Random
import numpy as np
from psychopy import event, clock, visual
from psychopy.visual import TextStim
from psychopy.visual.rect import Rect
from psychopy.tools.monitorunittools import convertToPix, cm2pix
from neurobooth_os.tasks.task import Eyelink_HostPC, TaskAborted, EyelinkColor


class SDMT(Eyelink_HostPC):
    def __init__(
            self,
            n_trials: int,
            symbols: List[str],
            seed: Optional[int],
            text_height: float,
            text_font: str,
            cell_size: float,
            grid: (int, int),
            mouse_visible: bool,
            interline_gap: float,
            **kwargs
    ):
        """
        :param n_trials: The number of trials, where each trial presents a new random grid of test symbols
        :param symbols: The symbols to be displayed in the key (in order of presentation)
        :param seed: If provided, controls the "random" sequence of generated test symbols
        :param text_height: The height of the text (cm)
        :param text_font: The font of the text
        :param cell_size: The size of each square cell (cm)
        :param grid: Specifies the number of rows and columns in the test symbol grid
        :param mouse_visible: Whether the mouse should be visible during the task
        :param interline_gap: How much space to add between each row of test symbols (cm)
        :param kwargs: Passthrough arguments
        """
        super().__init__(**kwargs)

        self.n_trials: int = n_trials
        self.symbols = np.array(symbols, dtype='U1')

        # Visual Parameters
        self.text_height: float = text_height
        self.text_font: str = text_font
        self.cell_size: float = cell_size
        self.grid: (int, int) = grid
        self.interline_gap: float = interline_gap
        self.mouse_visible: bool = mouse_visible

        # Sequence Parameters
        self.seed: int = seed if (seed is not None) else randint(0, 1<<20)
        self.rng = Random(self.seed)
        self.test_sequence: np.ndarray = np.array([])

        self._calc_symbol_locations()

    def _calc_symbol_locations(self) -> None:
        grow, gcol = self.grid
        grid_width = gcol * self.cell_size
        key_width = len(self.symbols) * self.cell_size
        total_height = grow * (self.cell_size + self.interline_gap)  # Test area height
        total_height += self.cell_size * 2 + self.interline_gap # Keys area height

        # Key Area
        h = (total_height / 2) - (self.cell_size / 2)
        w = (-key_width / 2) + (self.cell_size / 2)
        self.key_symbol_locs = [(w + i*self.cell_size, h) for i in range(len(self.symbols))]
        h -= self.cell_size
        self.key_number_locs = [(w + i*self.cell_size, h) for i in range(len(self.symbols))]

        # Test Area
        h -= self.cell_size + self.interline_gap * 2
        w = (-grid_width / 2) + (self.cell_size / 2)
        self.test_symbol_locs = []
        for j in range(grow):
            self.test_symbol_locs.append([(w + i*self.cell_size, h) for i in range(gcol)])
            h -= self.cell_size + self.interline_gap

    def generate_test_sequence(self) -> np.ndarray:
        h, w = self.grid
        seq = np.full(h*w, ' ', dtype='U1')
        seq[0] = self.rng.choice(self.symbols)
        for i in range(h*w-1):
            seq[i+1] = self.rng.choice(np.setdiff1d(self.symbols, seq[i]))  # No back-to-back symbols
        return seq.reshape(self.grid)

    def draw_symbol(self, loc: (float, float), symbol: str) -> None:
        # Draw  symbol and box to screen
        rstim = Rect(self.win, size=self.cell_size, lineColor='black', units='cm', pos=loc)
        tstim = TextStim(
            self.win, text=symbol, font=self.text_font, height=self.text_height, units='cm', pos=loc
        )
        rstim.draw()
        tstim.draw()

        # Draw box to EyeLink tablet
        x, y = convertToPix(loc, loc, 'cm', self.win)
        x, y = int(round(x)), int(round(y))
        cell_size_px = int(round(cm2pix(self.cell_size, self.win)))
        self.draw_box(x, y, cell_size_px, cell_size_px, EyelinkColor.BLACK)

    def draw_key(self) -> None:
        for symbol, loc in zip(self.symbols, self.key_symbol_locs):
            self.draw_symbol(loc, symbol)

        for i, loc in enumerate(self.key_number_locs):
            self.draw_symbol(loc, f'{i+1}')

    def draw_test_grid(self) -> None:
        for i, row in enumerate(self.test_symbol_locs):
            for j, loc in enumerate(row):
                self.draw_symbol(loc, self.test_sequence[i, j])

    def draw(self) -> None:
        self.draw_key()
        self.draw_test_grid()
        self.win.flip()

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


if __name__ == "__main__":
    from psychopy import monitors
    from neurobooth_os.config import load_config_by_service_name

    load_config_by_service_name('STM')

    monitor_width = 55
    monitor_distance = 60
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=monitor_distance
    )
    win = visual.Window(
        [1920, 1080], fullscr=False, monitor=customMon, units="pix", color="white"
    )

    self = SDMT(
        win=win,
        n_trials=1,
        symbols=[
            '\u2A05',
            '\u223E',
            '\u22B2',
            '\u22B3',
            '\u2A06',
            '\u221D',
            '\u2238',
            '\u2ADB',
            '\u2200',
        ],
        seed=0,
        text_height=1.5,
        text_font='Arial',
        cell_size=1.75,
        grid=(8, 20),
        mouse_visible=False,
        interline_gap=0.75,
    )
    self.run()
    win.close()
