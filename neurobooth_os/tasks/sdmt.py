import os
from typing import List, Optional, Union
from random import randint, Random
import numpy as np

from psychopy import event, clock
from psychopy.core import CountdownTimer
from psychopy.visual import TextStim, ImageStim
from psychopy.visual.rect import Rect

from neurobooth_os.tasks.task import Eyelink_HostPC, TaskAborted, EyelinkColor
from neurobooth_os.iout.stim_param_reader import get_cfg_path


class SDMT(Eyelink_HostPC):
    def __init__(
            self,
            duration: float,
            symbols: List[str],
            seed: Optional[int],
            text_height: float,
            continue_text_height: float,
            text_font: str,
            cell_size: float,
            grid_rows: int,
            grid_cols: int,
            practice_grid_rows: int,
            practice_grid_cols: int,
            mouse_visible: bool,
            interline_gap: float,
            draw_on_tablet: bool = True,
            **kwargs
    ):
        """
        :param duration: The duration of the task (seconds)
        :param symbols: The symbols to be displayed in the key (in order of presentation)
        :param seed: If provided, controls the "random" sequence of generated test symbols
        :param text_height: The height of the text (cm)
        :param continue_text_height: The height of the text for the continue message (cm)
        :param text_font: The font of the text
        :param cell_size: The size of each square cell (cm)
        :param grid_rows: The number of rows in the test symbol grid
        :param grid_cols: The number of columns in the test symbol grid
        :param grid_rows: The number of rows in the test symbol grid (for practice)
        :param grid_cols: The number of columns in the test symbol grid (for practice)
        :param mouse_visible: Whether the mouse should be visible during the task
        :param interline_gap: How much space to add between each row of test symbols (cm)
        :param draw_on_tablet: Whether to draw the grid to the EyeLink tablet.
        :param kwargs: Passthrough arguments
        """
        super().__init__(**kwargs)

        self.duration: float = duration
        self.symbols = np.array(symbols, dtype='U1')

        # Visual Parameters
        self.text_height: float = text_height
        self.continue_text_height: float = continue_text_height
        self.text_font: str = text_font
        self.cell_size: float = cell_size
        self.grid: (int, int) = (grid_rows, grid_cols)
        self.practice_grid: (int, int) = (practice_grid_rows, practice_grid_cols)
        self.interline_gap: float = interline_gap
        self.mouse_visible: bool = mouse_visible
        self.draw_on_tablet: bool = draw_on_tablet

        # Dynamically calculated cell center positions
        self.key_symbol_locs: List[(float, float)] = []
        self.key_number_locs: List[(float, float)] = []
        self.test_symbol_locs: List[List[(float, float)]] = []
        self.continue_message_loc: (float, float) = (0, 0)

        # Sequence Parameters
        self.seed: int = seed if (seed is not None) else randint(0, 1<<20)
        self.rng = Random(self.seed)
        self.test_sequence: np.ndarray = np.array([])

    def calc_symbol_locations(self, practice: bool) -> None:
        grid = self.practice_grid if practice else self.grid
        grow, gcol = grid

        grid_width = gcol * self.cell_size
        key_width = len(self.symbols) * self.cell_size
        total_height = grow * (self.cell_size + self.interline_gap)  # Test area height
        total_height += self.cell_size * 2 + self.interline_gap  # Keys area height
        total_height += self.interline_gap*2 + self.continue_text_height  # Continue message height

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

        # Continue message
        h -= (self.interline_gap * 2) + (self.continue_text_height / 2)
        self.continue_message_loc = (0, h)

    def generate_test_sequence(self, practice: bool) -> np.ndarray:
        grid = self.practice_grid if practice else self.grid
        h, w = grid

        seq = np.full(h*w, ' ', dtype='U1')
        seq[0] = self.rng.choice(self.symbols)
        for i in range(h*w-1):
            seq[i+1] = self.rng.choice(np.setdiff1d(self.symbols, seq[i]))  # No back-to-back symbols
        return seq.reshape(grid)

    def draw_symbol(self, loc: (float, float), symbol: str) -> None:
        # Draw  symbol and box to screen
        rstim = Rect(self.win, size=self.cell_size, lineColor='black', units='cm', pos=loc)
        tstim = TextStim(
            self.win, text=symbol, font=self.text_font, height=self.text_height, units='cm', pos=loc
        )
        rstim.draw()
        tstim.draw()

        if self.draw_on_tablet: # Draw box to EyeLink tablet
            # Just accessing the vertices directly to sidestep a PsychoPy error
            vertices = [self.pos_psych2pix(v) for v in rstim.verticesPix]
            xs, ys = [x for (x, y) in vertices], [y for (x, y) in vertices]
            x, y = min(xs), min(ys)
            size = max(xs) - x

            self.draw_box(x, y, size, size, EyelinkColor.BLACK)

    def draw_key(self) -> None:
        for symbol, loc in zip(self.symbols, self.key_symbol_locs):
            self.draw_symbol(loc, symbol)

        for i, loc in enumerate(self.key_number_locs):
            self.draw_symbol(loc, f'{i+1}')

    def draw_test_grid(self) -> None:
        for i, row in enumerate(self.test_symbol_locs):
            for j, loc in enumerate(row):
                self.draw_symbol(loc, self.test_sequence[i, j])

    def draw_continue_message(self) -> None:
        stim = TextStim(
            self.win,
            text='Press continue for the next slide',
            font=self.text_font,
            height=self.continue_text_height,
            units='cm',
            pos=self.continue_message_loc,
            wrapWidth=30*self.continue_text_height,  # Avoid wrapping
        )
        stim.draw()

    def draw(self) -> None:
        if self.draw_on_tablet:
            self.clear_screen(EyelinkColor.BRIGHTWHITE)

        self.draw_key()
        self.draw_test_grid()
        self.draw_continue_message()
        self.win.flip()

    @classmethod
    def asset_path(cls, asset: Union[str, os.PathLike]) -> str:
        """
        Get the path to the specified asset.
        :param asset: The name of the asset/file.
        :return: The file system path to the asset in the config folder.
        """
        return os.path.join(get_cfg_path('assets'), 'SDMT', asset)

    def show_slide(self, name: str) -> None:
        slide = ImageStim(
            self.win,
            image=SDMT.asset_path(f'{name}.jpg'),
            pos=(0, 0),
            size=(2, 2),
            units="norm",
        )
        slide.draw()
        self.win.flip()

    def wait_for_advance(self) -> None:
        event.clearEvents(eventType='keyboard')
        while not event.getKeys(self.advance_keys):
            self.check_if_aborted()
            clock.wait(0.05, hogCPUperiod=1)

    def new_frame(self) -> None:
        self.draw_on_tablet = False  # Don't spend time redrawing the tablet grid
        self.sendMessage(self.marker_trial_end, to_marker=True, add_event=True)
        self.test_sequence = self.generate_test_sequence(practice=False)
        self.draw()
        self.sendMessage(self.marker_trial_start, to_marker=True, add_event=True)

    def run_trial(self) -> None:
        self.test_sequence = self.generate_test_sequence(practice=False)
        self.calc_symbol_locations(practice=False)
        self.draw()

        event.clearEvents(eventType='keyboard')
        self.sendMessage(self.marker_trial_start, to_marker=True, add_event=True)
        timer = CountdownTimer(self.duration)
        while timer.getTime() > 0:
            self.check_if_aborted()
            if event.getKeys(self.advance_keys):
                self.new_frame()
                continue
            clock.wait(0.05, hogCPUperiod=1)
        self.sendMessage(self.marker_trial_end, to_marker=True, add_event=True)


    def run_practice_trial(self) -> None:
        self.show_slide('before_practice')
        self.wait_for_advance()

        self.test_sequence = self.generate_test_sequence(practice=True)
        self.calc_symbol_locations(practice=True)
        self.draw()

        self.sendMessage(self.marker_practice_trial_start, to_marker=True, add_event=True)
        self.wait_for_advance()
        self.sendMessage(self.marker_practice_trial_end, to_marker=True, add_event=True)

        self.show_slide('after_practice')
        self.wait_for_advance()

    def present_task(self, prompt=True, duration=0, **kwargs):
        self.Mouse.setVisible(self.mouse_visible)
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        try:
            self.run_practice_trial()
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


def test_script() -> None:
    from psychopy import monitors, visual
    from neurobooth_os.config import load_config_by_service_name

    load_config_by_service_name('STM')

    monitor_width = 55
    monitor_distance = 60
    customMon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=monitor_distance
    )
    win = visual.Window(
        [1920, 1080], fullscr=False, monitor=customMon, units="pix", color="white"
    )

    self = SDMT(
        win=win,
        duration=90,
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
        text_height=2.2, continue_text_height=1, text_font='Arial', cell_size=2.5, interline_gap=1,
        grid_rows=4, grid_cols=12, practice_grid_rows=2, practice_grid_cols=6,
        mouse_visible=False, draw_on_tablet=False,
    )
    self.run()
    win.close()


if __name__ == "__main__":
    test_script()
