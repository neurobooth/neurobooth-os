"""
The MOT task is composed of a sequence of "frames".
Each frame is responsible for either 1) displaying an image to the screen or 2) animating a single MOT trial.
At many points during MOT, it is possible for study staff to abort the task (i.e., skip the remainder of it).

Frames are responsible for visual presentation to the screen.
For example, MOT.frame should handle flashing circles and actually drawing them to the screen.
However, MOT.animate handles the logical model of each circle and manages _HOW_ their positions update.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Tuple, NamedTuple, Union, Literal
from typing_extensions import Annotated
from pydantic import BaseModel, Field

from psychopy import visual
from psychopy.clock import Clock, wait, CountdownTimer
from psychopy.event import Mouse
from psychopy.visual import TextBox2

from neurobooth_os.tasks import utils
from neurobooth_os.tasks.MOT.animate import CircleAnimator, SavedAnimationHandler, CircleModel

if TYPE_CHECKING:  # Prevent circular import during runtime
    from neurobooth_os.tasks.MOT.task import MOT

# ========================================================================
# Parameter Definitions
# ========================================================================
class ImageFrameParameters(BaseModel):
    image_path: str


TRIAL_TYPE = Literal['example', 'practice', 'test']


class TrialFrameParameters(BaseModel):
    trial_type: TRIAL_TYPE = 'test'
    animation_path: str
    n_targets: Annotated[int, Field(ge=1)]
    flash_duration: Annotated[float, Field(gt=0)] = 3
    flash_frequency: Annotated[float, Field(gt=0)] = 0.2
    movement_duration: Annotated[float, Field(gt=0)] = 5
    click_timeout: Annotated[float, Field(gt=0)] = 60
    circle_base_color: str = 'black'
    circle_flash_color: str = 'cyan'
    circle_correct_color: str = 'cyan'
    circle_incorrect_color: str = 'red'


FrameParameters = Union[ImageFrameParameters, TrialFrameParameters]


class FrameChunk(BaseModel):
    chunk_name: str
    frames: List[FrameParameters]


# ========================================================================
# Frame Implementations
# ========================================================================
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
        self.wait_key = 'space'   # System waits for this key, but the key ends the waiting and continues the session

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
    def __init__(self, window: visual.Window, task: MOT, image_name: str):
        """
        :param window: The PsychoPy window to draw to.
        :param task: The MOT task object
        :param image_name: The name of the image to display. (The image should be in MOT/assets.)
        """
        super().__init__(window)
        image_path = task.asset_path(image_name, 'MOT')
        self.stimulus = visual.ImageStim(self.window, image=image_path, pos=(0, 0), units="deg")

    def run(self) -> None:
        self.present_stimuli([self.stimulus], wait_for_key=self.wait_key)


class CircleStimulus:
    """The stimulus object (that is drawn to the screen) that wraps a CircleModel."""
    def __init__(
            self,
            model: CircleModel,
            window: visual.Window,
            color: str,
    ):
        """
        Create a new stimulus wrapping the logical model.

        :param model: The logical model of the circle's position.
        :param window: The window object the stimulus will be presented on.
        :param color: The color of the circle
        """
        self.model = model
        self.color = color

        self.stimulus = visual.Circle(
            window,
            self.model.radius,
            pos=self.screen_position(),
            lineColor="black",
            fillColor=self.color,
            units="pix",
        )

    def screen_position(self) -> Tuple[float, float]:
        """
        Translate logical circle coordinates to the appropriate screen coordinates.
        :returns: The screen coordinates of the circle.
        """
        return self.model.x - self.model.paper_size // 2, self.model.y - self.model.paper_size // 2

    def update_stimulus(self) -> visual.BaseVisualStim:
        """
        Update the PsychoPy stimulus representing this circle.
        :return: The PsychoPy stimulus object.
        """
        self.stimulus.pos = self.screen_position()
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
    trial_count: int
    n_circles: int
    n_targets: int
    n_correct: int
    click_duration: float
    circle_mean_speed: float
    circle_std_speed: float
    animation_duration: float
    state: str


class TrialFrame(MOTFrame):
    """Runs a single MOT trial (circles are presented, some flash, circles move, and the subject clicks.)"""
    # Define trial type for generation of results CSV
    trial_type: TRIAL_TYPE = 'test'

    def __init__(
            self,
            window: visual.Window,
            task: MOT,
            trial_count: int,
            trial_param: TrialFrameParameters,
    ):
        """
        :param window: The PsychoPy window to draw to.
        :param task: The MOT task object.
        :param trial_count: The number of the trial in a sequence of trials.
        :param trial_param: Structured representation of all necessary trial frame parameters.
        """
        super().__init__(window)
        self.task = task
        self._allow_clicks = True
        self._log_results = True

        # Time-related properties of the stimulus
        self.flash_duration = trial_param.flash_duration
        self.flash_frequency = trial_param.flash_frequency
        self.movement_duration = trial_param.movement_duration
        self.click_timeout = trial_param.click_timeout

        # Load a pre-saved animation
        self.animation: CircleAnimator = SavedAnimationHandler().load(
            self.task.animation_path(trial_param.animation_path)  # Get the full path to the animation
        ).get_replay()

        # Visual properties of the stimulus
        self.trial_count = trial_count
        self.n_targets = trial_param.n_targets
        self.circle_base_color = trial_param.circle_base_color
        self.circle_flash_color = trial_param.circle_flash_color
        self.circle_correct_color = trial_param.circle_correct_color
        self.circle_incorrect_color = trial_param.circle_incorrect_color
        self.circles = [CircleStimulus(c, self.window, self.circle_base_color) for c in self.animation.circles]
        self.background = visual.Rect(
            self.window,
            width=self.animation.paper_size,
            height=self.animation.paper_size,
            lineColor="black",
            fillColor="white",
            units="pix",
        )

        # Settings for the trial information message at the bottom of the stimulus
        self.trial_count_message = f'Trial {self.trial_count} of 6'
        self.score_message = f'Score {{score}}'
        self.click_message = f'Click {self.n_targets} dots'
        self.animation_message = ''
        self.__current_message = ''

        # Set appropriate marker entries for this trial
        self.start_marker = task.marker_trial_start
        self.end_marker = task.marker_trial_end

        # Keep track of trial performance
        self.click_info: List[ClickInfo] = []
        self.actual_animation_duration: float = -1
        self.completed: bool = False
        self.result_status: str = 'click'

    def run(self) -> None:
        self.result_status = 'click'
        self.completed = False
        self.__current_message = self.animation_message
        self.send_marker(self.start_marker)
        self.send_marker(f"number targets:{self.n_targets}")

        # Present moving circles
        clock = Clock()
        self.task.Mouse.setVisible(0)  # Hide mouse
        self.initial_placement()
        self.flash_targets()
        self.show_moving_circles()
        self.actual_animation_duration = round(clock.getTime(), 2)

        if not self._allow_clicks:  # Skip click handler for example frame
            self.completed = True
            self.send_marker(self.end_marker)
            return

        # Allow participants to click on the circles
        self.__current_message = self.click_message
        self.present_circles(send_location=False)  # Show updated message to screen
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
            self.completed = True
            if self._log_results:
                self.task.log_result(self.results())
            self.update_score(-sum([c.correct for c in self.click_info]))
            self.click_info = []
            self.run()  # Repeat the trial
            return

        self.send_marker(self.end_marker)
        self.completed = True
        if self._log_results:
            self.task.log_result(self.results())
        wait(0.5)

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

    def trial_info_message(self) -> List[visual.TextStim]:
        offset = self.animation.paper_size // 2
        stimuli = []
        if self.__current_message:
            stimuli.append(visual.TextStim(
                self.window, text=self.__current_message, color="blue", height=40,
                alignText='center', alignHoriz='center', anchorVert='top', pos=(0, -offset-10), units="pix",
            ))
        if self.trial_count_message:
            stimuli.append(visual.TextStim(
                self.window, text=self.trial_count_message, color="blue", height=40,
                alignText='left', alignHoriz='left', anchorVert='bottom', pos=(-offset, offset+10), units="pix",
            ))
        if self.score_message:
            score_message = self.score_message.format(score=self.task.score)
            stimuli.append(visual.TextStim(
                self.window, text=score_message, color="blue", height=40,
                alignText='right', alignHoriz='right', anchorVert='bottom', pos=(offset, offset+10), units="pix",
            ))
        return stimuli

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
                letterHeight=1.5,
                text=message,
                font="Arial",
                borderColor=None,
                fillColor=None,
                editable=False,
                alignment="center",
            )
        ], wait_for_key=self.wait_key)

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
        for message in self.trial_info_message():
            stimuli.append(message)
        self.present_stimuli(stimuli)

    def initial_placement(self) -> None:
        self.animation.initial_placement()
        for circle in self.circles:
            circle.color = self.circle_base_color
        self.present_circles()

    def flash_targets(self) -> None:
        countdown = CountdownTimer()
        countdown.add(self.flash_duration)
        target_circles = self.circles[:self.n_targets]
        while countdown.getTime() > 0:
            for circle in target_circles:
                circle.color = self.circle_flash_color
            self.present_circles(send_location=False)
            wait(self.flash_frequency)

            for circle in target_circles:
                circle.color = self.circle_base_color
            self.present_circles(send_location=False)
            wait(self.flash_frequency)

            self.task.check_if_aborted()

    def show_moving_circles(self) -> None:
        clock = Clock()
        while clock.getTime() < self.movement_duration:
            self.animation.step(clock.getTime())
            self.present_circles()
            self.task.check_if_aborted()
        self.animation.step(self.movement_duration)  # Ensure consistent endpoint for precomputed trajectory
        self.present_circles()

    def handle_clicks(self) -> None:
        """
        Handle participant clicks on the targets. Reveals correct and incorrect clicks, up to the number of targets.
        """
        self.task.Mouse.setVisible(1)  # Show mouse

        mouse = Mouse(win=self.window)
        mouse.mouseClock = Clock()
        timeout_clock = Clock()

        n_clicks = 0
        prev_button_state = None
        mouse.clickReset()
        while n_clicks < self.n_targets:
                
            buttons, click_times = mouse.getPressed(getTime=True)
            left_button_click, left_button_click_time = buttons[0] > 0, click_times[0]

            if left_button_click and buttons != prev_button_state:
                for i, circle in enumerate(self.circles):
                    if not mouse.isPressedIn(circle.stimulus):
                        continue
                    elif i in [c.circle_idx for c in self.click_info]:  # Ignore if circle was previously clicked
                        continue

                    n_clicks += 1
                    is_correct = i < self.n_targets
                    if is_correct:
                        self.update_score(1)
                        circle.color = self.circle_correct_color
                    else:
                        circle.color = self.circle_incorrect_color

                    x, y = mouse.getPos()
                    self.task.sendMessage(self.task.marker_response_start)
                    self.click_info.append(
                        ClickInfo(circle_idx=i, x=x, y=y, time=left_button_click_time, correct=is_correct)
                    )

                    self.present_circles(send_location=False)
                    mouse.clickReset()  # Reset click timer
                    break

            prev_button_state = buttons
            wait(0.001, hogCPUperiod=1)

            self.task.check_if_aborted()
            if timeout_clock.getTime() > self.click_timeout:
                raise TrialTimeout()

        self.task.Mouse.setVisible(0)  # Hide mouse

    def results(self) -> TrialResult:
        """
        :return: Results of the trial to be saved in the results CSV
        """
        mean_speed, std_speed = self.animation.get_circle_speeds()
        mean_speed, std_speed = mean_speed.mean(), std_speed.mean()  # Avg. across circles
        return TrialResult(
            n_circles=len(self.circles),
            n_targets=self.n_targets,
            n_correct=sum([c.correct for c in self.click_info]),
            circle_mean_speed=mean_speed,
            circle_std_speed=std_speed,
            animation_duration=self.actual_animation_duration,
            click_duration=max([0, *[c.time for c in self.click_info]]),
            state='aborted' if not self.completed else self.result_status,
            trial_type=self.trial_type,
            trial_count=self.trial_count,
        )


class ExampleFrame(TrialFrame):
    """Show an example of the moving dots"""
    trial_type = 'example'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._allow_clicks = False
        self._log_results = False

        # Disable the message at the top/bottom of the stimulus area
        self.click_message = ''
        self.animation_message = ''
        self.score_message = ''
        self.trial_count_message = ''

    def send_marker(self, marker: str) -> None:
        pass  # Disable sending messages to the marker stream

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
        self._log_results = False  # This class will handle result logging after calling super.run()

        # Set a different message to display at the bottom of the stimulus area
        self.click_message = f'Click the {self.n_targets} dots that were blue'
        self.animation_message = ''
        self.score_message = ''
        self.trial_count_message = ''

        # Set appropriate marker entries for this trial
        self.start_marker = self.task.marker_practice_trial_start
        self.end_marker = self.task.marker_practice_trial_end

        self.max_attempts = max_attempts

    def update_score(self, delta: int) -> None:
        pass  # Disable score updates

    def run(self) -> None:
        for i in range(self.max_attempts):
            self.click_info = []
            super().run()

            n_correct = sum([c.correct for c in self.click_info])
            if (n_correct < self.n_targets) and (i < self.max_attempts-1):
                self.result_status = 'repeat'
                self.task.log_result(self.results())
                self.present_alert(
                    "Let's try again.\n"
                    f"When the movement stops, click the {self.n_targets} dots that flashed."
                )
            else:
                self.present_alert(f"You got {n_correct} of {self.n_targets} dots correct.")
                self.task.log_result(self.results())
                break
