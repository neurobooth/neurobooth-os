import os.path as op
import random
import math
from abc import ABC, abstractmethod
from typing import List, Optional, Union, NamedTuple

import pandas as pd
from psychopy import visual
from psychopy.visual.textbox2 import TextBox2
from itertools import chain

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task_Eyetracker


class TaskAborted(Exception):
    """
    Exception raised when the task is aborted
    """
    pass


def check_if_aborted(keys=("q",)) -> None:
    """
    Check to see if a task has been aborted. If so, raise an exception.
    :param keys: The keys that will abort a task.
    """
    if event.getKeys(keyList=keys):
        print("MOT Task aborted")  # Send message to CTR
        raise TaskAborted()


class MOTFrame(ABC):
    """
    The MOT task is composed of a sequence of frames.
    Each frame is a single trial or image/message that needs to be advanced through.
    """
    def __init__(self, window: visual.Window):
        """
        Create a new frame.
        :param window: The PsychoPy window to draw to.
        """
        self.window = window
        self.wait_key = 'space'

    @abstractmethod
    def run(self) -> None:
        raise NotImplementedError()

    def present_stimuli(
            self,
            stimuli: List[Optional[visual.BaseVisualStim]],
            wait_for_key: Optional[str] = None,
    ) -> None:
        """
        Present a series of stimuli and (optionally) wait for a specified key press.
        :param stimuli: The stimuli to draw to the window.
        :param wait_for_key: If specified, block until the specified key is pressed.
        """
        # For convenience: filter out None types
        stimuli = [stim for stim in stimuli if stim is not None]

        # Draw stimuli to the screen
        for stim in stimuli:
            stim.draw()
        self.window.flip()

        # Wait for the key press if specified
        if wait_for_key is not None:
            utils.get_keys(keyList=[wait_for_key])


class ImageFrame(MOTFrame):
    """Presents a single image to the window and waits for the space bar to be pressed."""
    def __init__(self, window: visual.Window, image_path: str):
        """
        :param window: The PsychoPy window to draw to.
        :param image_path: The path to the image to display.
        """
        super().__init__(window)
        self.stimulus = visual.ImageStim(self.window, image=image_path, pos=(0, 0), units="deg")

    def run(self) -> None:
        self.present_stimuli([self.stimulus], wait_for_key=self.wait_key)


class Circle:
    """Represents a single circle in an MOT trial."""
    def __init__(self, radius: float, paper_size: float, color: str = 'black'):
        """
        Create a new circle with random position and direction.

        :param radius: The radius of the circle (px).
        :param paper_size: The edge length of the square drawing area (px).
        :param color: The color of the circle
        """
        self.radius = radius
        self.paper_size = paper_size
        self.color = color
        self.x = 0
        self.y = 0

        # Random placement and direction; order is important to keep same RNG sequence
        self.random_reposition()
        self.direction = random.random() * 2 * math.pi

        self.stimulus = None

    def random_reposition(self) -> None:
        """Randomly reposition the circle."""
        self.x = random.random() * (self.paper_size - 2.0 * self.radius) + self.radius
        self.y = random.random() * (self.paper_size - 2.0 * self.radius) + self.radius

    def distance_to(self, other: 'Circle') -> float:
        """
        Compute the distance to another circle.
        :param other: The other circle.
        :return: The distance between circle centers (px).
        """
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)

    def make_simulus(self, window: visual.Window) -> visual.BaseVisualStim:
        """
        Make the PsychoPy stimulus representing this circle.
        :param window: The window object the stimulus will be presented on.
        :return: The PsychoPy stimulus object.
        """
        self.stimulus = visual.Circle(
            window,
            self.radius,
            pos=(self.x - self.paper_size // 2, self.y - self.paper_size // 2),
            lineColor="black",
            fillColor=self.color,
            units="pix",
        )
        return self.stimulus

    def update_stimulus(self) -> visual.BaseVisualStim:
        """
        Update the PsychoPy stimulus representing this circle.
        :return: The PsychoPy stimulus object.
        """
        self.stimulus.pos = (self.x - self.paper_size // 2, self.y - self.paper_size // 2)
        self.stimulus.color = self.color
        return self.stimulus


class TrialTimeout(Exception):
    """Exception to be raised when a participant takes too long to complete the click portion of the task."""
    pass


class ClickInfo(NamedTuple):
    """Contains information about a registered mouse click"""
    circle_idx: int
    x: float
    y: float
    time: float
    correct: bool


class TrialResult(NamedTuple):
    """Contains information about subject performance during the trial"""
    trial_type: str
    n_circles: int
    n_targets: int
    n_correct: int
    click_duration: float
    circle_speed: float
    velocity_noise: float
    random_seed: Union[str, int]
    animation_duration: float
    state: str


class TrialFrame(MOTFrame):
    """Runs a single MOT trial (circles are presented, some flash, circles move, and the subject clicks.)"""
    trial_type = 'test'

    def __init__(
            self,
            window: visual.Window,
            task: 'MOT',
            *,  # Remaining arguments must be by keyword
            flash_duration: float,
            movement_duration: float,
            click_timeout: float,
            trial_count: int,
            n_circles: int,
            n_targets: int,
            paper_size: float,
            circle_radius: float,
            circle_speed: float,
            velocity_noise: float,
            random_seed: Union[int, str],
    ):
        """
        :param window: The PsychoPy window to draw to.
        :param task: The MOT task object.
        :param flash_duration: How long the cirlces should flash green (s).
        :param movement_duration: The duration of circle movement (s).
        :param click_timeout: How long to wait for all clicks before timing out (s).
        :param trial_count: The number of the trial in a sequence of trials.
        :param n_circles: The total number of circles in the trial.
        :param n_targets: The number of circles that are designated as targets.
        :param paper_size: The width or height of the square stimulus area (px).
        :param circle_radius: The radius of each circle (px).
        :param circle_speed: The speed at which the circles move (px/s).
        :param velocity_noise: Noise applied to the velocity vectors during circle motion (deg).
        :param random_seed: A seed for the RNG to ensure consistency across sessions.
        """
        super().__init__(window)
        self.task = task

        # Time-related properties of the stimulus
        self.flash_duration = flash_duration
        self.movement_duration = movement_duration
        self.click_timeout = click_timeout

        # Visual properties of the stimulus
        self.trial_count = trial_count
        self.trial_info_str = ''
        self.n_circles = n_circles
        self.n_targets = n_targets
        self.paper_size = paper_size
        self.circles: List[Circle] = []
        self.background = visual.Rect(
            self.window,
            width=self.paper_size,
            height=self.paper_size,
            lineColor="black",
            fillColor="white",
            units="pix",
        )

        # Properties regarding circle positioning and movement
        self.circle_radius = circle_radius
        self.circle_repulsion = circle_radius * 5  # Repulsion during setup is 5 times radius
        self.circle_speed = circle_speed
        self.velocity_noise = velocity_noise * math.pi / 180  # deg -> rad
        self.random_seed = random_seed

        # Set appropriate marker entries for this trial
        self.start_marker = task.marker_trial_start
        self.end_marker = task.marker_trial_end

        # Keep track of trial performance
        self.click_info: List[ClickInfo] = []
        self.actual_animation_duration: float = -1
        self.completed: bool = False
        self.result_status: str = 'click'

    def run(self) -> None:
        self.send_marker(self.start_marker)
        self.send_marker(f"number targets:{self.n_targets}")

        # Set the random seed for this trial
        random.seed(self.random_seed)

        # Present moving circles
        clock = core.Clock()
        self.circle_repulsion = self.circle_radius * 5  # Reflecting inconsistency in this value in prior code
        self.setup_circles()
        self.circle_repulsion = self.circle_radius * 4  # Reflecting inconsistency in this value in prior code
        self.move_circles()  # Initial movement is holdover from prior code to preserve RNG sequence
        self.present_circles()
        self.flash_targets()
        self.show_moving_circles()
        self.actual_animation_duration = round(clock.getTime(), 2)

        # Allow participants to click on the circles
        try:
            self.handle_clicks()
        except TrialTimeout:
            self.send_marker(self.end_marker)
            self.present_alert(
                "You took too long to respond!\n"
                "Remember: once the movement stops,\n"
                "click the dots that flashed."
            )
            self.result_status = 'timeout'
            self.update_score(-sum([c.correct for c in self.click_info]))
            self.click_info = []
            self.run()  # Repeat the trial
            return

        self.send_marker(self.end_marker)
        self.completed = True
        utils.countdown(0.5)

    def send_marker(self, marker: str) -> None:
        """
        Send a message to the marker time-series.
        :param marker: The marker message to send
        """
        # This is a very simple method, but is provided so that it can be disabled via override
        self.task.sendMessage(marker)

    def update_score(self, delta: int) -> None:
        """
        Update the task's score.
        :param delta: The amount to change the score by.
        """
        # This is a very simple method, but is provided so that it can be disabled via override
        self.task.score += delta

    def trial_info_message(self) -> Optional[visual.TextStim]:
        message = f" {self.trial_count} of 6. {self.trial_info_str}   Score {self.task.score}"
        return visual.TextStim(self.window, text=message, pos=(0, -8), units="deg", color="blue")

    def present_alert(self, message: str) -> None:
        """
        Present an alert to the screen.
        :param message: The text of the alert
        """
        self.present_stimuli([
            self.task.continue_message,
            TextBox2(
                self.window,
                pos=(0, 0),
                color="black",
                units="deg",
                lineSpacing=0.9,
                letterHeight=1,
                text=message,
                font="Arial",
                borderColor=None,
                fillColor=None,
                editable=False,
                alignment="center",
            )
        ], wait_for_key=self.wait_key)

    def setup_circles(self) -> None:
        """Randomly initialize circle start positions and movement directions."""
        self.circles = [Circle(self.circle_radius, self.paper_size) for _ in range(self.n_circles)]

        # Enforce proximity limits
        # TODO: Original code incorrectly excluded last circle from loop. See if we want to keep fix wrt RNG sequence.
        for i, circle in enumerate(self.circles[1:]):
            # The below loop will always run at least once. It was originally coded this way, and keeping this
            # behavior maintains the same RNG sequence.
            too_close = True
            while too_close:
                circle.random_reposition()
                too_close = any([  # Check to see if the circle is still to close to another circle
                    circle.distance_to(other_circle) < self.circle_repulsion
                    for other_circle in self.circles[:i+1]
                ])

        # Make stimulus objects
        for circle in self.circles:
            circle.make_simulus(self.window)

    def present_circles(self, send_location: bool = True) -> None:
        """
        Present the background, circles, and info message to the screen.
        :param send_location: If true, send the target location to the eye tracker.
        """
        stimuli = [self.background]
        for i, circle in enumerate(self.circles):
            stim = circle.update_stimulus()
            stimuli.append(stim)
            if send_location:
                self.task.send_target_loc(stim.pos, target_name=f"target_{i}")
        stimuli.append(self.trial_info_message())
        self.present_stimuli(stimuli)

    def flash_targets(self) -> None:
        countdown = core.CountdownTimer()
        countdown.add(self.flash_duration)
        target_circles = self.circles[:self.n_targets]
        while countdown.getTime() > 0:
            for circle in target_circles:
                circle.color = 'green'
            self.present_circles(send_location=False)

            utils.countdown(0.1)

            for circle in target_circles:
                circle.color = 'black'
            self.present_circles(send_location=False)

            utils.countdown(0.1)
            check_if_aborted()

    def show_moving_circles(self) -> None:
        clock = core.Clock()
        while clock.getTime() < self.movement_duration:
            self.move_circles()
            self.present_circles()
            check_if_aborted()

    def move_circles(self) -> None:
        """
        Move the circles in preparation for the next PsychoPy frame.
        - Add noise to the velocity vector
        - Bounce circles off elastic boundaries
        - Avoid collisions between circles
        All computations are done outside the DOM.
        """
        for i, circle in enumerate(self.circles):
            old_x, old_y = circle.x, circle.y  # Save old coordinates
            new_dir = circle.direction + random.uniform(-1, 1) * self.velocity_noise  # Apply noise to direction

            # Compute Cartesian velocity vector and apply it
            vel_x = math.cos(new_dir) * self.circle_speed
            vel_y = math.sin(new_dir) * self.circle_speed
            circle.x, circle.y = old_x + vel_x, old_y + vel_y

            # Avoid collisions
            for j, other_circle in enumerate(self.circles):
                if i == j:  # Skip self
                    continue

                # Look ahead one step: if it collides, then update the direction until no collision or timeout
                for _ in range(1000):
                    if circle.distance_to(other_circle) < self.circle_repulsion:
                        # Could use uniform(-1, 1), but this way preserves old RNG sequence
                        new_dir += random.choice([-1, 1]) * random.uniform(0, 1) * math.pi

                        # Compute Cartesian velocity vector and apply it
                        vel_x = math.cos(new_dir) * self.circle_speed
                        vel_y = math.sin(new_dir) * self.circle_speed
                        circle.x, circle.y = old_x + vel_x, old_y + vel_y

            # Enforce elastic boundaries
            if circle.x >= (self.paper_size - circle.radius) or circle.x <= circle.radius:
                # Bounce off left/right boundaries
                vel_x *= -1
                circle.x = old_x + vel_x
            if circle.y >= (self.paper_size - circle.radius) or circle.y <= circle.radius:
                # Bounce off top/bottm boundaries
                vel_y *= -1
                circle.y = old_y + vel_y

            # Compute final direction and update
            circle.direction = math.atan2(vel_y, vel_x)  # Use atan2 (not atan)!

    def handle_clicks(self) -> None:
        """
        Handle participant clicks on the targets. Reveals correct and incorrect clicks, up to the number of targets.
        """
        self.task.Mouse.setVisible(1)  # Show mouse

        mouse = event.Mouse(win=self.window)
        mouse.mouseClock = core.Clock()
        timeout_clock = core.Clock()

        n_clicks = 0
        prev_button_state = None
        while n_clicks < self.n_targets:
            mouse.clickReset()
            buttons, click_time = mouse.getPressed(getTime=True)

            if sum(buttons) > 0 and buttons != prev_button_state:
                for i, circle in enumerate(self.circles):
                    if not mouse.isPressedIn(circle.stimulus):
                        continue
                    elif i in [c.circle_idx for c in self.click_info]:  # Ignore if circle was previously clicked
                        continue

                    n_clicks += 1
                    is_correct = i < self.n_targets
                    if is_correct:
                        self.update_score(1)
                        circle.color = "green"
                    else:
                        circle.color = "red"

                    x, y = mouse.getPos()
                    self.task.sendMessage(self.task.marker_response_start)
                    self.click_info.append(ClickInfo(circle_idx=i, x=x, y=y, time=click_time, correct=is_correct))

                    mouse.mouseClock = core.Clock()
                    self.present_circles(send_location=False)
                    break

            prev_button_state = buttons
            utils.countdown(0.001)

            check_if_aborted()
            if timeout_clock.getTime() > self.click_timeout:
                raise TrialTimeout()

        self.task.Mouse.setVisible(0)  # Hide mouse

    def results(self) -> TrialResult:
        """
        :return: Results of the trial to be saved in the results CSV
        """
        return TrialResult(
            n_circles=self.n_circles,
            n_targets=self.n_targets,
            n_correct=sum([c.correct for c in self.click_info]),
            circle_speed=self.circle_speed,
            velocity_noise=self.velocity_noise,
            trial_seed=self.random_seed,
            animation_duration=self.actual_animation_duration,
            click_duration=max(0, *[c.time for c in self.click_info]),
            state='aborted' if not self.completed else self.result_status,
            trial_type=self.trial_type,
        )


class ExampleFrame(TrialFrame):
    """Show an example of the moving dots"""
    trial_type = 'example'

    def send_marker(self, marker: str) -> None:
        pass  # Disable sending messages to the marker stream

    def trial_info_message(self) -> Optional[visual.TextStim]:
        return None  # The example has no info message

    def update_score(self, delta: int) -> None:
        pass  # Disable score updates


class PracticeFrame(TrialFrame):
    """Run a practice trial"""
    trial_type = 'practice'

    def __init__(self, *args, max_attempts: int = 2, **kwargs):
        """
        :param max_attempts: The maximum number of practice attempts.
        """
        super().__init__(*args, **kwargs)

        # Set appropriate marker entries for this trial
        self.start_marker = self.task.marker_practice_trial_start
        self.end_marker = self.task.marker_practice_trial_end

        self.max_attempts = max_attempts

    def trial_info_message(self) -> Optional[visual.TextStim]:
        message = f"Click the {self.n_targets} dots that were green"
        return visual.TextStim(self.window, text=message, pos=(0, -8), units="deg", color="blue")

    def update_score(self, delta: int) -> None:
        pass  # Disable score updates

    def run(self) -> None:
        for _ in range(self.max_attempts):
            self.click_info = []
            super().run()

            n_correct = sum([c.correct for c in self.click_info])
            if n_correct < self.n_targets:
                self.present_alert(
                    "Let's try again.\n"
                    f"When the movement stops, click the {self.n_targets} dots that flashed."
                )
            else:
                self.present_alert(f"You got {n_correct} of {self.n_targets} dots correct.")
                break


class MOT(Task_Eyetracker):
    def __init__(
        self,
        path: str = "",
        subj_id: str = "test",
        task_name: str = "MOT",
        numCircles: int = 10,
        time_presentation: float = 3,
        trial_duration: float = 5,
        clickTimeout: float = 60,
        seed: int = 2,
        **kwargs,
    ):
        """
        :param path: Output path for the task reslults.
        :param subj_id: The subject ID.
        :param task_name: The name of this task.
        :param numCircles: The total number of circles to draw.
        :param time_presentation: How long the targets flash black and green.
        :param trial_duration: How long the circles move fot.
        :param clickTimeout: How long to wait for all clicks to be completed before timing out.
        :param seed: Seed used to initialize the random number sequence controlling all test trials.
        """
        super().__init__(**kwargs)

        self.root_dir = op.join(neurobooth_os.__path__[0], "tasks", "MOT")
        self.output_path = path
        self.task_name = task_name
        self.subject_id = subj_id
        self.n_circles = numCircles
        self.move_duration = trial_duration
        self.flash_duration = time_presentation
        self.click_timeout = clickTimeout
        self.seed = seed
        self.paper_size = 500  # size of stimulus graphics page

        self.win.color = "white"
        self.win.flip()

        self.score: int = 0
        self.n_repetitions: int = 0
        self._init_frame_sequence()

    def _init_frame_sequence(self) -> None:
        """Create the sequences of frames that compose this task"""
        self.continue_message = visual.ImageStim(
            self.win,
            image=op.join(self.root_dir, "continue.png"),
            pos=(0, 0),
            units="deg",
        )

        common_trial_kwargs = {
            'flash_duration': self.flash_duration,
            'movement_duration': self.move_duration,
            'click_timeout': self.click_timeout,
            'n_circles': self.n_circles,
            'paper_size': self.paper_size,
            'circle_radius': 15,
            'velocity_noise': 15,
        }

        self.intro_chunk: List[MOTFrame] = [
            ImageFrame(self.win, 'intro.png'),
            ImageFrame(self.win, 'inst1.png'),
            ExampleFrame(
                self.win, self,
                n_targets=2, circle_speed=0.5, trial_count=0, random_seed='example1',
                **common_trial_kwargs
            ),
            ImageFrame(self.win, 'inst2.png'),
            PracticeFrame(
                self.win, self,
                n_targets=2, circle_speed=0.5, trial_count=0, random_seed='practice1',
                **common_trial_kwargs
            ),
            ImageFrame(self.win, 'inst3.png'),
            PracticeFrame(
                self.win, self,
                n_targets=2, circle_speed=0.5, trial_count=0, random_seed='practice2',
                **common_trial_kwargs
            ),
        ]

        self.chunk_3tgt: List[MOTFrame] = [ImageFrame(self.win, 'targ3.png')]
        self.chunk_4tgt: List[MOTFrame] = [ImageFrame(self.win, 'targ4.png')]
        self.chunk_5tgt: List[MOTFrame] = [ImageFrame(self.win, 'targ5.png')]

        for i in range(6):
            speed = i + 1
            trial_count = i + 1

            seed = self.seed + i
            self.chunk_3tgt.append(TrialFrame(
                self.win, self,
                n_targets=3, circle_speed=speed, trial_count=trial_count, random_seed=seed,
                **common_trial_kwargs
            ))

            seed = self.seed + i + 10
            self.chunk_4tgt.append(TrialFrame(
                self.win, self,
                n_targets=4, circle_speed=speed, trial_count=trial_count, random_seed=seed,
                **common_trial_kwargs
            ))

            seed = self.seed + i + 20
            self.chunk_5tgt.append(TrialFrame(
                self.win, self,
                n_targets=5, circle_speed=speed, trial_count=trial_count, random_seed=seed,
                **common_trial_kwargs
            ))

    def run(self, prompt=True, last_task=False, subj_id="test", **kwargs):
        self.subject_id = subj_id
        if self.n_repetitions > 0:
            self._init_frame_sequence()  # Create new frames for repeats to flush old data

        self.score = 0
        self.present_instructions(prompt)
        self.win.color = "white"
        self.win.flip()
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        try:
            self.run_chunk(self.intro_chunk)
            self.run_chunk(self.chunk_3tgt)
            self.run_chunk(self.chunk_4tgt)
            self.run_chunk(self.chunk_5tgt)
        except TaskAborted:
            print('MOT aborted')
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True)

        self.save_results()

        if prompt:  # Check if task should be repeated
            func_kwargs_func = {"prompt": prompt}
            self.n_repetitions += 1
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.run,
                func_kwargs=func_kwargs_func,
                waitKeys=False,
            )

        self.present_complete(last_task)
        return self.events

    @staticmethod
    def run_chunk(chunk: List[MOTFrame]) -> None:
        for frame in chunk:
            frame.run()

    def save_results(self):
        results: List[TrialResult] = [
            frame.results()
            for frame in chain(self.intro_chunk, self.chunk_3tgt, self.chunk_4tgt, self.chunk_5tgt)
            if isinstance(frame, TrialFrame) and frame.trial_type in ['test', 'practice']
        ]
        results_df = pd.DataFrame(results, columns=TrialResult._fields)

        test_results = results_df.loc[(results_df['trial_type'] == 'test') & (results_df['state'] == 'click')]
        total_targets = test_results['n_targets'].sum()
        total_hits = test_results['n_correct'].sum()
        total_click_duration = test_results['click_duration'].sum()
        outcome_df = pd.DataFrame.from_dict({
            'score': self.score,
            'pct_correct': round(total_hits / total_targets, 3),
            'total_click_duration': round(total_click_duration, 1),
        }, orient="index", columns=["vals"])

        repetition_str = f'_rep-{self.n_repetitions}' if self.n_repetitions > 0 else ''
        result_fname = f"{self.subject_id}_{self.task_name}_results_v2{repetition_str}.csv"
        outcome_fname = f"{self.subject_id}_{self.task_name}_outcomes_v2{repetition_str}.csv"
        results_df.to_csv(self.output_path + result_fname)
        outcome_df.to_csv(self.output_path + outcome_fname)
        if len(self.task_files):
            self.task_files = self.task_files[-1] + f", {result_fname}, {outcome_fname}" + "}"
        else:
            self.task_files += "{" + f"{result_fname}, {outcome_fname}" + "}"


if __name__ == "__main__":
    from psychopy import sound, core, event, monitors, visual, monitors

    monitor_width = 55
    monitor_distance = 60
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=monitor_distance
    )
    win = visual.Window(
        [1920, 1080], fullscr=False, monitor=customMon, units="pix", color="white"
    )

    self = MOT(win=win)
    self.run()
    win.close()
