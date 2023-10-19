import os.path as op
import random
import math
import time
from abc import ABC, abstractmethod
from typing import List, Optional

from numpy import sqrt
import pandas as pd
from psychopy import core, visual, event
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
        self.present_stimuli([self.stimulus], wait_for_key='space')


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


class TrialFrame(MOTFrame):
    """Runs a single MOT trial (circles are presented, some flash, circles move, and the subject clicks.)"""
    def __init__(
            self,
            window: visual.Window,
            task: 'MOT',
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
            random_seed: int,
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

        # Keep track of the score
        self.score: int = 0

        # Set appropriate marker entries for this trial
        self.start_marker = task.marker_trial_start
        self.end_marker = task.marker_trial_end

    def run(self) -> None:
        self.task.sendMessage(self.start_marker)
        self.task.sendMessage(f"number targets:{self.n_targets}")

        random.seed(self.random_seed)  # Set the random seed for this trial

        clock = core.Clock()
        self.setup_circles()
        self.circle_repulsion = self.circle_radius * 4  # Reflecting inconsistency in this value in prior code
        self.move_circles()  # Initial movement is holdover from prior code to preserve RNG sequence
        self.present_circles()
        self.flash_targets()
        self.show_moving_circles()
        actual_duration = round(clock.getTime(), 2)

        # clicks, ncorrect, rt = self.clickHandler(
        #     circle, frame["n_targets"], frame["type"]
        # )
        #
        self.task.sendMessage(self.end_marker)
        utils.countdown(0.5)
        #
        # state = "click"
        # if rt == "timeout":
        #     # rewind frame sequence by one frame, so same frame is displayed again
        #     self.frameSequence.insert(0, frame)
        #
        #     msg_alert = (
        #             "You took too long to respond!\nRemember: once the movement stops,\n"
        #             + "click the dots that flashed."
        #     )
        #     msg_stim = self.my_textbox2(msg_alert)
        #     self.present_stim([self.continue_msg, msg_stim], "space")
        #
        #     # set timout variable values
        #     state = "timeout"
        #     rt = 0
        #     ncorrect = 0
        #     if frame["type"] == "test" and self.trialCount > 0:
        #         self.trialCount -= 1
        #
        # elif frame["type"] == "practice" and rt != "aborted":
        #     msg = f"You got {ncorrect} of {frame['n_targets']} dots correct."
        #     if ncorrect < frame["n_targets"]:
        #
        #         if practiceErr < 2:  # up to 2 practice errors
        #             # rewind frame sequence by one frame, so same frame is displayed again
        #             self.frameSequence.insert(0, frame)
        #             msg = (
        #                     "Let's try again. \nWhen the movement stops,"
        #                     + f"click the {frame['n_targets']} dots that flashed."
        #             )
        #
        #             practiceErr += 1
        #     else:
        #         practiceErr = 0
        #     msg_stim = self.my_textbox2(msg)
        #     self.present_stim([self.continue_msg, msg_stim], "space")
        #
        # elif rt == "aborted":
        #     state = "aborted"
        #     rt = 0
        #     ncorrect = 0
        #
        # frame["rt"] = rt
        # frame["ncorrect"] = ncorrect
        # frame["clicks"] = clicks
        # frame["trueDuration"] = actual_duration
        #
        # if frame["type"] == "test":
        #     total += frame["n_targets"]
        #
        # results.append(
        #     {
        #         "type": frame["type"],  # one of practice or test
        #         "hits": ncorrect,
        #         "rt": rt,
        #         "numTargets": frame["n_targets"],
        #         "numdots": frame["n_circles"],
        #         "speed": self.mycircle["speed"],
        #         "noise": self.mycircle["noise"],
        #         "duration": trueDuration,
        #         "state": state,
        #         "seed": frame["message"],
        #     }
        # )
        #
        # if frame["type"] == "test":
        #     self.trialCount += 1

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

    def trial_info_message(self) -> Optional[visual.TextStim]:
        message = f" {self.trial_count} of 6. {self.trial_info_str}   Score {self.score}"
        return visual.TextStim(self.window, text=message, pos=(0, -8), units="deg", color="blue")

    def handle_clicks(self) -> None:
        """
        Handle participant clicks on the targets. Reveals correct and incorrect clicks, up to the number of targets.
        """
        mouse = event.Mouse(win=self.window)
        self.task.Mouse.setVisible(1)
        mouse.mouseClock = core.Clock()
        mouse.clickReset()
        trial_clock = core.Clock()

        n_clicks, prev_button_state = 0, None
        clicks, n_correct = [], 0
        while n_clicks < self.n_targets:
            mouse.clickReset()
            buttons, time_click = mouse.getPressed(getTime=True)
            rt = trial_clock.getTime()

            if sum(buttons) > 0 and buttons != prev_button_state:
                for i, c in enumerate(circle):
                    if mouse.isPressedIn(c):
                        # Check not clicked on previous circle
                        if i in [clk[0] for clk in clicks]:
                            continue
                        x, y = mouse.getPos()
                        self.sendMessage(self.marker_response_start)
                        clicks.append([i, x, y, time_click])
                        n_clicks += 1
                        mouse.mouseClock = core.Clock()
                        if i < n_targets:
                            n_correct += 1
                            c.color = "green"
                            if frame_type == "test":
                                self.score += 1
                        else:
                            c.color = "red"
                        if frame_type in ["test", "practice"]:
                            stim = circle + self.trial_info_msg(frame_type)
                        else:
                            stim = circle
                        self.present_stim(self.background + stim)

                        break
            prev_button_state = buttons
            utils.countdown(0.001)

            aborted = self.abort_task()
            if aborted:
                rt = "aborted"
                break

            if rt > self.clickTimeout:
                rt = "timeout"
                break
        self.Mouse.setVisible(0)
        return clicks, n_correct, rt


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
        super().__init__(**kwargs)

        self.path_out = path
        self.task_name = task_name
        self.subj_id = subj_id
        self.mycircle = {
            "x": [],  # circle x
            "y": [],  # circle y
            "d": [],  # circle motion direction in deg
            "r": 15,  # circle radius
            "z": 4,  # circle repulsion radius
            "noise": 15,  # motion direction noise in deg
            "speed": 2,
        }  # circle speed in pixels/frame

        self.numCircles = numCircles  # total # of circles
        self.duration = trial_duration  # desired duration of trial in s
        self.time_presentation = time_presentation  # duration green dots presentation
        self.clickTimeout = clickTimeout  # timeout for clicking on targets

        self.seed = seed  # For repeatable random numbers
        self.paperSize = 500  # size of stimulus graphics page

        self.trialCount = 0
        self.score = 0
        self.trial_info_str = ""
        self.rootdir = op.join(neurobooth_os.__path__[0], "tasks", "MOT")
        self.rep = ""
        self.task_files = ""
        self.setup(self.win)

    def setup(self, win):

        self.win.color = "white"
        self.win.flip()
        self.background = [
            visual.Rect(
                self.win,
                width=self.paperSize,
                height=self.paperSize,
                lineColor="black",
                fillColor="white",
                units="pix",
            )
        ]
        # create the trials chain
        self.frameSequence = self.setFrameSequence()

    def trial_info_msg(self, msg_type=None):
        if msg_type == "practice":
            msg = self.trial_info_str
        elif msg_type == "test":
            msg = f" {self.trialCount + 1} of 6. {self.trial_info_str}   Score {self.score}"
        else:
            msg = f" {self.trialCount + 1} of 6. {' '*len(self.trial_info_str)}   Score {self.score}"
        return [
            visual.TextStim(self.win, text=msg, pos=(0, -8), units="deg", color="blue")
        ]

    def my_textbox2(self, text, pos=(0, 0), size=(None, None)):
        tbx = TextBox2(
            self.win,
            pos=pos,
            color="black",
            units="deg",
            lineSpacing=0.9,
            letterHeight=1,
            text=text,
            font="Arial",  # size=(20, None),
            borderColor=None,
            fillColor=None,
            editable=False,
            alignment="center",
        )
        return tbx

    def present_stim(self, elems, key_resp=None):
        for e in elems:
            e.draw()
        self.win.flip()
        if key_resp is not None:
            utils.get_keys(keyList=[key_resp])

    def run(self, prompt=True, last_task=False, subj_id="test", **kwargs):

        self.score = 0
        self.abort = False

        # Check if run previously, create framesequence again
        if len(self.frameSequence) == 0:
            self.frameSequence = self.setFrameSequence()

        self.subj_id = subj_id
        self.present_instructions(prompt)
        self.win.color = "white"
        self.win.flip()
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        self.run_trials()
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True)

        if prompt:
            func_kwargs_func = {"prompt": prompt}
            self.rep += "_I"
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.run,
                func_kwargs=func_kwargs_func,
                waitKeys=False,
            )

        self.present_complete(last_task)
        return self.events

    # initialize the dots
    def setup_dots(self, numCircles):

        # initialize start positions and motion directions randomly
        x, y, d = [], [], []
        for i in range(numCircles):
            x.append(
                random.random() * (self.paperSize - 2.0 * self.mycircle["r"])
                + self.mycircle["r"]
            )
            y.append(
                random.random() * (self.paperSize - 2.0 * self.mycircle["r"])
                + self.mycircle["r"]
            )
            d.append(random.random() * 2 * math.pi)

        self.mycircle["x"] = x
        self.mycircle["y"] = y
        self.mycircle["d"] = d
        repulsion = self.mycircle["z"] * self.mycircle["r"]
        # enforce proximity limits
        for i in range(1, numCircles - 1):
            # reposition each circle until outside repulsion area of all other circles
            tooClose = True
            while tooClose:

                self.mycircle["x"][i] = (
                    random.random() * (self.paperSize - 2.0 * self.mycircle["r"])
                    + self.mycircle["r"]
                )
                self.mycircle["y"][i] = (
                    random.random() * (self.paperSize - 2.0 * self.mycircle["r"])
                    + self.mycircle["r"]
                )

                # repulsion distance defaults to 5 times the circle's radius
                tooClose = False
                for j in range(i):
                    if i == j:
                        continue
                    dist = math.sqrt(
                        (self.mycircle["x"][i] - self.mycircle["x"][j]) ** 2
                        + (self.mycircle["y"][i] - self.mycircle["y"][j]) ** 2
                    )
                    if dist < (5 * self.mycircle["r"]):
                        # print(i, j, dist)
                        tooClose = True
                        break

        # when done, update the circles on the DOM
        circle = []
        for i in range(numCircles):
            circle.append(
                visual.Circle(
                    self.win,
                    self.mycircle["r"],
                    pos=(self.mycircle["x"][i], self.mycircle["y"][i]),
                    lineColor="black",
                    fillColor="black",
                    units="pix",
                )
            )

        return circle

    def moveCircles(self, circle):
        """Update the position of the circles for the next frame
        - add noise to the velocity vector
        - bounce circles off elastic boundaries
        - avoid collisions b/w circles
        all computations are done outside the DOM

        Returns
        -------
        """

        timeout = 0
        noise = (self.mycircle["noise"] * math.pi) / 180  # angle to rad
        repulsion = self.mycircle["z"] * self.mycircle["r"]

        numCircles = len(self.mycircle["x"])
        for i in range(numCircles):
            # save the current dot's coordinates
            oldX = self.mycircle["x"][i]
            oldY = self.mycircle["y"][i]

            # update direction vector with noise
            newD = self.mycircle["d"][i] + random.uniform(0, 1) * 2.0 * noise - noise

            # compute x and y shift
            velocityX = math.cos(newD) * self.mycircle["speed"]
            velocityY = math.sin(newD) * self.mycircle["speed"]

            # compute new x and y coordinates
            newX = oldX + velocityX
            newY = oldY + velocityY

            # avoid collisions
            for j in range(numCircles):  # i, numCircles):
                # skip self
                if j == i:
                    continue

                # look ahead one step: if next move collides, update direction til no collision or timeout
                timeout = 0
                while timeout < 1000:
                    timeout += 1
                    dist = math.sqrt(
                        (newX - self.mycircle["x"][j]) ** 2
                        + (newY - self.mycircle["y"][j]) ** 2
                    )

                    if dist < repulsion:
                        # update vector direction
                        newD += random.choice([-1, 1]) * random.uniform(0, 1) * math.pi
                        # recompute  x shift and x coordinate
                        velocityX = math.cos(newD) * self.mycircle["speed"]
                        # recompute  y shift and y coordinate
                        velocityY = math.sin(newD) * self.mycircle["speed"]
                        if dist < math.sqrt(
                            ((oldX + velocityX) - self.mycircle["x"][j]) ** 2
                            + ((oldY + velocityY) - self.mycircle["y"][j]) ** 2
                        ):
                            newX = oldX + velocityX
                            newY = oldY + velocityY
                    else:
                        break
                    if timeout == 1000:
                        print(f"time out {j} {i} d = {dist}")

            # enforce elastic boundaries
            if (
                newX >= (self.paperSize - self.mycircle["r"])
                or newX <= self.mycircle["r"]
            ):
                # bounce off left or right boundaries
                velocityX *= -1  # invert x component of velocity vector
                newX = oldX + velocityX  # recompute new x coordinate

            if (
                newY >= (self.paperSize - self.mycircle["r"])
                or newY <= self.mycircle["r"]
            ):
                # bounce off top or bottom boundaries
                velocityY *= -1  # invert y component of velocity vector
                newY = oldY + velocityY  # recompute new y coordinate

            # assign new coordinates to each circle
            self.mycircle["x"][i] = newX
            self.mycircle["y"][i] = newY

            # compute final vector direction
            # use atan2 (not atan)!
            self.mycircle["d"][i] = math.atan2(velocityY, velocityX)

            # now we update the DOM elements
            circle[i].pos = [newX - self.paperSize // 2, newY - self.paperSize // 2]
            circle[i].draw()
            self.send_target_loc(circle[i].pos, target_name=f"target_{i}")

        return circle

    def clickHandler(self, circle, n_targets, frame_type):

        # this handler listens for clicks on the targets
        # reveals correct and incorrect clicks
        # stops listening after numTargets clicks
        # gives feedback and paces the trial presentation

        mouse = event.Mouse(win=self.win)
        self.Mouse.setVisible(1)
        mouse.mouseClock = core.Clock()
        mouse.clickReset()
        trialClock = core.Clock()

        n_clicks, prevButtonState = 0, None
        clicks, ncorrect = [], 0
        while n_clicks < n_targets:
            mouse.clickReset()
            buttons, time_click = mouse.getPressed(getTime=True)
            rt = trialClock.getTime()

            if sum(buttons) > 0 and buttons != prevButtonState:
                for i, c in enumerate(circle):
                    if mouse.isPressedIn(c):
                        # Check not clicked on previous circle
                        if i in [clk[0] for clk in clicks]:
                            continue
                        x, y = mouse.getPos()
                        self.sendMessage(self.marker_response_start)
                        clicks.append([i, x, y, time_click])
                        n_clicks += 1
                        mouse.mouseClock = core.Clock()
                        if i < n_targets:
                            ncorrect += 1
                            c.color = "green"
                            if frame_type == "test":
                                self.score += 1
                        else:
                            c.color = "red"
                        if frame_type in ["test", "practice"]:
                            stim = circle + self.trial_info_msg(frame_type)
                        else:
                            stim = circle
                        self.present_stim(self.background + stim)

                        break
            prevButtonState = buttons
            utils.countdown(0.001)

            aborted = self.abort_task()
            if aborted:
                rt = "aborted"
                break

            if rt > self.clickTimeout:
                rt = "timeout"
                break
        self.Mouse.setVisible(0)
        return clicks, ncorrect, rt

    def abort_task(self, keys=["q"]):
        if event.getKeys(keyList=keys):
            self.frameSequence = []
            self.abort = True
            return True
        return False

    def showMovingDots(self, frame):

        numTargets = frame["n_targets"]
        self.mycircle["speed"] = frame["speed"]
        duration = frame["duration"]
        frame_type = frame["type"]

        # set the random seed for each trial
        random.seed(frame["message"])

        circle = self.setup_dots(frame["n_circles"])
        circle = self.moveCircles(circle)

        if frame_type == "test":
            self.present_stim(self.trial_info_msg())
        else:
            self.win.flip()

        # initialize the dots, flashgreen colors
        countDown = core.CountdownTimer()
        countDown.add(self.time_presentation)

        while countDown.getTime() > 0:
            for n in range(numTargets):
                circle[n].color = "green"
            if frame_type == "test":
                self.present_stim(self.background + circle + self.trial_info_msg())
            else:
                self.present_stim(self.background + circle)
            utils.countdown(0.1)

            for n in range(numTargets):
                circle[n].color = "black"

            if frame_type == "test":
                self.present_stim(self.background + circle + self.trial_info_msg())
            else:
                self.present_stim(self.background + circle)
            utils.countdown(0.1)

            abort = self.abort_task()
            if abort:
                print("MOT Task aborted")
                return circle

        clock = core.Clock()
        while clock.getTime() < duration:
            circle = self.moveCircles(circle)
            if frame_type == "test":
                self.present_stim(self.background + circle + self.trial_info_msg())
            else:
                self.present_stim(self.background + circle)

            abort = self.abort_task()
            if abort:
                print("MOT Task aborted")
                return circle

        return circle

    def run_trials(self):
        results = []

        total = 0
        practiceErr = 0
        while len(self.frameSequence):
            # read the frame sequence one frame at a time
            frame = self.frameSequence.pop(0)

            # check if it's the startup frame
            if frame["type"] in ["begin", "message"]:
                self.present_stim(frame["message"], "space")
                continue

            # else show the animation
            if self.trialCount == 6:
                self.trialCount = 0

            if frame["type"] == "practice":
                self.trial_info_str = (
                    f"Click the {frame['n_targets']} dots that were green"
                )
                self.sendMessage(self.marker_practice_trial_start)
                self.sendMessage(f"number targets:{frame['n_targets']}")

            elif frame["type"] == "test":
                self.trial_info_str = f"Click {frame['n_targets']} dots"
                self.sendMessage(self.marker_trial_start)
                self.sendMessage(f"number targets:{frame['n_targets']}")
            else:
                circle = self.showMovingDots(frame)
                continue

            clockDuration = core.Clock()
            circle = self.showMovingDots(frame)
            if self.abort:
                continue
            trueDuration = round(clockDuration.getTime(), 2)

            msg_stim = self.trial_info_msg(frame["type"])
            self.present_stim(self.background + circle + msg_stim)

            clicks, ncorrect, rt = self.clickHandler(
                circle, frame["n_targets"], frame["type"]
            )

            if frame["type"] == "test":
                self.sendMessage(self.marker_trial_end)
            elif frame["type"] == "practice":
                self.sendMessage(self.marker_practice_trial_end)

            utils.countdown(0.5)

            state = "click"
            if rt == "timeout":
                # rewind frame sequence by one frame, so same frame is displayed again
                self.frameSequence.insert(0, frame)

                msg_alert = (
                    "You took too long to respond!\nRemember: once the movement stops,\n"
                    + "click the dots that flashed."
                )
                msg_stim = self.my_textbox2(msg_alert)
                self.present_stim([self.continue_msg, msg_stim], "space")

                # set timout variable values
                state = "timeout"
                rt = 0
                ncorrect = 0
                if frame["type"] == "test" and self.trialCount > 0:
                    self.trialCount -= 1

            elif frame["type"] == "practice" and rt != "aborted":
                msg = f"You got {ncorrect} of {frame['n_targets']} dots correct."
                if ncorrect < frame["n_targets"]:

                    if practiceErr < 2:  # up to 2 practice errors
                        # rewind frame sequence by one frame, so same frame is displayed again
                        self.frameSequence.insert(0, frame)
                        msg = (
                            "Let's try again. \nWhen the movement stops,"
                            + f"click the {frame['n_targets']} dots that flashed."
                        )

                        practiceErr += 1
                else:
                    practiceErr = 0
                msg_stim = self.my_textbox2(msg)
                self.present_stim([self.continue_msg, msg_stim], "space")

            elif rt == "aborted":
                state = "aborted"
                rt = 0
                ncorrect = 0

            frame["rt"] = rt
            frame["ncorrect"] = ncorrect
            frame["clicks"] = clicks
            frame["trueDuration"] = trueDuration

            if frame["type"] == "test":
                total += frame["n_targets"]

            results.append(
                {
                    "type": frame["type"],  # one of practice or test
                    "hits": ncorrect,
                    "rt": rt,
                    "numTargets": frame["n_targets"],
                    "numdots": frame["n_circles"],
                    "speed": self.mycircle["speed"],
                    "noise": self.mycircle["noise"],
                    "duration": trueDuration,
                    "state": state,
                    "seed": frame["message"],
                }
            )

            if frame["type"] == "test":
                self.trialCount += 1

        # the sequence is empty, we are done!

        rtTotal = [
            r["rt"]
            for r in results
            if r["type"] != "practice"
            and r["state"] != "timeout"
            and r["state"] != "aborted"
        ]

        outcomes = {}
        outcomes["score"] = self.score
        outcomes["correct"] = round(self.score / total, 3) if total else 0
        outcomes["rtTotal"] = round(sum(rtTotal), 1)

        # SAVE RESULTS to file
        df_res = pd.DataFrame(results)
        df_out = pd.DataFrame.from_dict(outcomes, orient="index", columns=["vals"])
        res_fname = f"{self.subj_id}_{self.task_name}_results{self.rep}.csv"
        out_fname = f"{self.subj_id}_{self.task_name}_outcomes{self.rep}.csv"
        df_res.to_csv(self.path_out + res_fname)
        df_out.to_csv(self.path_out + out_fname)

        if len(self.task_files):
            self.task_files = self.task_files[-1] + f", {res_fname}, {out_fname}" + "}"
        else:
            self.task_files += "{" + f"{res_fname}, {out_fname}" + "}"

    def setFrameSequence(self):
        testMessage = {
            "begin": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "intro.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "instruction1": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "inst1.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "practice2": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "inst2.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "practice3": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "inst3.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "targets3": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "targ3.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "targets4": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "targ4.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "targets5": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "targ5.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
        }
        self.continue_msg = visual.ImageStim(
            self.win,
            image=op.join(self.rootdir, "continue.png"),
            pos=(0, 0),
            units="deg",
        )

        # set the random generator's seed
        s = self.seed

        frame_type = [
            "begin",
            "message",
            "example",
            "message",
            "practice",
            "message",
            "practice",
        ]

        frame_message = [
            testMessage["begin"],
            testMessage["instruction1"],
            "example1",
            testMessage["practice2"],
            "practice1",
            testMessage["practice3"],
            "practice2",
        ]

        frame_ntargets = [0, 0, 2, 0, 2, 0, 3]
        frame_speed = [0, 0, 0.5, 0, 0.5, 0, 0.5]
        frameSequence = []
        # instructions and practice phase
        for i in range(len(frame_type)):
            frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": frame_ntargets[i],
                    "n_circles": self.numCircles,
                    "speed": frame_speed[i],
                    "duration": 3,
                    "message": frame_message[i],
                }
            )

        # test 3 dots
        frame_type = ["message", "test", "test", "test", "test", "test", "test"]
        frame_message = [
            testMessage["targets3"],
            s,
            s + 1,
            s + 2,
            s + 3,
            s + 4,
            s + 5,
            s + 6,
        ]

        frame_speed = [0, 1, 2, 3, 4, 5, 6]
        for i in range(len(frame_type)):
            frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": 3,
                    "n_circles": self.numCircles,
                    "speed": frame_speed[i],
                    "duration": self.duration,
                    "message": frame_message[i],
                }
            )

        # test 4 dots
        frame_message = [
            testMessage["targets4"],
            s + 10,
            s + 11,
            s + 12,
            s + 13,
            s + 14,
            s + 15,
            s + 16,
        ]
        for i in range(len(frame_type)):
            frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": 4,
                    "n_circles": self.numCircles,
                    "speed": frame_speed[i],
                    "duration": self.duration,
                    "message": frame_message[i],
                }
            )

        # test 5 dots
        frame_message = [
            testMessage["targets5"],
            s + 20,
            s + 21,
            s + 22,
            s + 23,
            s + 24,
            s + 25,
            s + 26,
        ]
        for i in range(len(frame_type)):
            frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": 5,
                    "n_circles": self.numCircles,
                    "speed": frame_speed[i],
                    "duration": self.duration,
                    "message": frame_message[i],
                }
            )
        return frameSequence


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
