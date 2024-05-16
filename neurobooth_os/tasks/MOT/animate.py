"""
Handles the logical model of each circle in an MOT trial and logic for how the circles should move.
Presentation of circles to the screen should be handled by MOT.frame.
"""

import math
import random
import time
from abc import ABC, abstractmethod
from typing import Union, Optional, List
import numpy as np


class CircleModel:
    """Represents the position of a single circle in an MOT trial."""
    def __init__(self, radius: float, paper_size: float):
        """
        Create a new circle with random position and direction.

        :param radius: The radius of the circle (px).
        :param paper_size: The edge length of the square drawing area (px).
        """
        self.radius = radius
        self.paper_size = paper_size
        self.x, self.y = 0, 0
        self.direction = 0

    def random_reposition(self) -> None:
        """Randomly reposition the circle."""
        self.x = random.random() * (self.paper_size - 2.0 * self.radius) + self.radius
        self.y = random.random() * (self.paper_size - 2.0 * self.radius) + self.radius

    def random_direction(self) -> None:
        """Randomly pick a new direction of motion for the circle."""
        self.direction = random.random() * 2 * math.pi

    def distance_to(self, other: 'CircleModel') -> float:
        """
        Compute the distance to another circle.
        :param other: The other circle.
        :return: The distance between circle centers (px).
        """
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


class CircleAnimator(ABC):
    """This class is responsible for computing circle trajectories for a trial."""
    def __init__(self, n_circles: int, paper_size: float, circle_radius: float):
        """
        :param n_circles: The total number of circles in the trial.
        :param paper_size: The width or height of the square stimulus area (px).
        :param circle_radius: The radius of each circle (px).
        """
        self.paper_size = paper_size
        self.circle_radius = circle_radius
        self.circles = [CircleModel(circle_radius, paper_size) for _ in range(n_circles)]

        # Values related to circle speed tracking
        self._last_time: float = np.nan
        self._speed_history: List[np.ndarray] = []

    def initial_placement(self) -> None:
        """Place circles in their initial positions and reset speed history."""
        self._initial_placement()

        # Reset speed tracking state
        self._last_time = np.nan
        self._speed_history = []

    @abstractmethod
    def _initial_placement(self) -> None:
        raise NotImplementedError()

    def step(self, elapsed_time: float) -> None:
        """
        Advance the simulation to update circle positions. Update circle speed history.
        :param elapsed_time: Seconds elapsed since animation start.
        """
        prior_positions = np.array([(c.x, c.y) for c in self.circles], dtype='float64')
        self._step(elapsed_time)  # Perform the position update
        current_positions = np.array([(c.x, c.y) for c in self.circles], dtype='float64')

        delta_t = elapsed_time - self._last_time
        self._last_time = elapsed_time
        if np.isnan(delta_t):  # Do not try to track the first speed
            return

        delta_pos = np.linalg.norm(current_positions - prior_positions, axis=1)
        self._speed_history.append(delta_pos / delta_t)

    @abstractmethod
    def _step(self, elapsed_time: float) -> None:
        raise NotImplementedError()

    def get_circle_speeds(self) -> (np.ndarray, np.ndarray):
        """
        Calculate the mean and std of observed speed of each circle (px/s).
        -1 is used as a sentinel value if there is no speed history.
        :return: (mean, std) Array containing the mean and std of the observed speed of each circle (px/s).
        """
        if self._speed_history:
            return np.mean(self._speed_history, axis=0), np.std(self._speed_history, axis=0)
        else:
            sentinel = np.full(len(self.circles), -1, dtype='float64')
            return sentinel, sentinel


class StepwiseAnimator(CircleAnimator):
    """Step-by-step circle animation.
    Can be used for "live" animation, but the actual velocity / number of steps will vary based on system load.
    """
    def __init__(
            self,
            n_circles: int,
            paper_size: float,
            circle_radius: float,
            circle_speed: float,
            velocity_noise: float,
            random_seed: Union[int, str],
    ):
        """
        :param n_circles: The total number of circles in the trial.
        :param paper_size: The width or height of the square stimulus area (px).
        :param circle_radius: The radius of each circle (px).
        :param circle_speed: The speed at which the circles move (px/step).
        :param velocity_noise: Noise applied to the velocity vectors during circle motion (rad).
        :param random_seed: A seed for the RNG to ensure consistency across sessions.
        """
        super().__init__(n_circles, paper_size, circle_radius)
        self.circle_speed = circle_speed
        self.velocity_noise = velocity_noise
        self.circle_repulsion = circle_radius * 5
        self.random_seed = random_seed

    def _initial_placement(self) -> None:
        """Initialize circles to have random positions and directions."""
        random.seed(self.random_seed)
        for circle in self.circles:
            circle.random_reposition()
            circle.random_direction()

        # Enforce proximity limits
        for i, circle in enumerate(self.circles[1:]):
            while any([  # Check if too close to circles earlier in the array
                circle.distance_to(other_circle) < self.circle_repulsion
                for other_circle in self.circles[:(i+1)]
            ]):
                circle.random_reposition()

    def _step(self, elapsed_time: float = 0) -> None:
        """
        Move the circles one step in the animation.
        - Add noise to the velocity vector
        - Bounce circles off elastic boundaries
        - Avoid collisions between circles

        :param elapsed_time: Ignored in this animation implementation.
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
                    if circle.distance_to(other_circle) >= self.circle_repulsion:
                        break  # No collision detected, continue to next circle

                    # Alter direction to avoid collision
                    new_dir += random.uniform(-1, 1) * math.pi

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


class ReplayAnimator(CircleAnimator):
    """Replays a precomputed animation to allow for consistent/known speeds and trajectories"""
    def __init__(self, trajectories: np.ndarray, update_freq: int, paper_size: float, circle_radius: float):
        """
        Create an animator that replays a precomputed/saved trajectory.
        :param trajectories: An SxCx2 array, for S animation steps and C circles.
        :param update_freq: How many animation steps should occur per second.
        :param paper_size: The width or height of the square stimulus area (px).
        :param circle_radius: The radius of each circle (px).
        """
        self.trajectories = trajectories
        self.update_freq = update_freq
        super().__init__(n_circles=trajectories.shape[1], paper_size=paper_size, circle_radius=circle_radius)

    def _update_to_step(self, step: int) -> None:
        """
        Update all circle positions to the given animation step.
        :param step: The step (i.e., index into the trajectory array)
        """
        for i, circle in enumerate(self.circles):
            circle.x = self.trajectories[step, i, 0]
            circle.y = self.trajectories[step, i, 1]

    def _initial_placement(self) -> None:
        """Place circles in the first step of the replayed animation"""
        self._update_to_step(0)

    def _step(self, elapsed_time: float) -> None:
        """
        Place circles in their respective locations depending on the elapsed time.
        :param elapsed_time: Seconds elapsed since animation start.
        """
        step = int(np.rint(elapsed_time * self.update_freq))
        step = min(step, self.trajectories.shape[0]-1)  # Don't go past the end of the array
        self._update_to_step(step)


class UninitializedAnimationException(Exception):
    def __init__(self):
        super().__init__('Must call run_animation() or load() before save() or get_replay()')


class SavedAnimationHandler:
    """Create and load precomputed animations."""
    def __init__(self):
        # Parameters used to store a replay
        self.update_freq: Optional[int] = None
        self.trajectories: Optional[np.ndarray] = None

        # Additional parameters needed to initialize a CircleAnimator
        self.paper_size: Optional[float] = None
        self.circle_radius: Optional[float] = None

    def run_animation(
            self,
            animator: StepwiseAnimator,
            animation_duration: float,
            update_freq: int,
    ) -> None:
        """
        Run the given stepwise animation. The update frequency coupled with the speed parameter of the animation will
        determine the speed (in px/s) of the circles in the playback.
        :param animator: The animation to run.
        :param animation_duration: How many seconds to animate.
        :param update_freq: The intended update rate (Hz) of the playback.
        """
        # Save animator properties
        self.paper_size = animator.paper_size
        self.circle_radius = animator.circle_radius

        # Initialize replay variables
        self.update_freq = update_freq
        n_steps = int(np.ceil(update_freq * animation_duration))
        n_circles = len(animator.circles)
        self.trajectories = np.zeros((n_steps, n_circles, 2), dtype='float64')

        # Run animation and save circle trajectories
        animator.initial_placement()
        for s in range(n_steps):
            animator.step()
            for c, circle in enumerate(animator.circles):
                self.trajectories[s, c, 0] = circle.x
                self.trajectories[s, c, 1] = circle.y

    def _check_if_initialized(self) -> None:
        if self.update_freq is None or self.trajectories is None:
            raise UninitializedAnimationException()

    def save(self, path: str) -> 'SavedAnimationHandler':
        """
        Save the computed trajectories to a .npz file.
        :param path: The path to the intended file. The file should end in .npz.
        :return: This object, used for call chaining.
        """
        self._check_if_initialized()
        np.savez_compressed(
            path,
            update_freq=self.update_freq,
            trajectories=self.trajectories,
            circle_radius=self.circle_radius,
            paper_size=self.paper_size,
            created_at=time.time(),
        )
        return self

    def load(self, path: str) -> 'SavedAnimationHandler':
        """
        Load computed trajectories from a .npz file.
        :param path: The path to the file.
        :return: This object, used for call chaining.
        """
        data = np.load(path)
        self.update_freq = data['update_freq']
        self.trajectories = data['trajectories']
        self.circle_radius = data['circle_radius']
        self.paper_size = data['paper_size']
        return self

    def get_replay(self) -> ReplayAnimator:
        self._check_if_initialized()
        return ReplayAnimator(
            trajectories=self.trajectories,
            update_freq=self.update_freq,
            paper_size=self.paper_size,
            circle_radius=self.circle_radius,
        )
