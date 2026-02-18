# -*- coding: utf-8 -*-
"""
Utilities for executing tasks
"""

from __future__ import absolute_import, division

from typing import List, Optional

from psychopy import core, event, monitors, sound

import time
import os
import os.path as op
from typing import Union

from pylsl import local_clock
from psychopy import visual

from neurobooth_os.iout.stim_param_reader import get_cfg_path

text_continue = 'Please press:\n\t"Continue" to advance'
text_practice_screen = "Please practice the task \n\tPress any button when done"
text_task = "Please do the task \n\tPress any button when done"
text_end = "Thank you. You have completed this task"


def send_marker(marker, msg):
    marker.push_sample([f"{msg}_{time.time()}"])


class InvalidWindowRefreshRate(Exception):
    """An error signaling a window refresh rate that is out of specified bounds"""
    pass


def check_window_refresh_rate(win: visual.window.Window, min_rate: float, max_rate: float):
    """
    Measures the refresh rate of the window/screen, and raises an error if it is out of tolerances.
    :param win: The PsychoPy window object
    :param min_rate: The minimum acceptable refresh rate (Hz)
    :param max_rate: The maximum acceptable refresh rate (Hz)
    :return:
    """
    psychopy_rate = 1 / win.monitorFramePeriod
    actual_rate = win.getActualFrameRate(nIdentical=30, nMaxFrames=300, nWarmUpFrames=30, threshold=2)
    if actual_rate is None:
        raise InvalidWindowRefreshRate("Window frame rate measurement returned 'None'.")

    print(f"Monitor Refresh Rate: Psychopy est. = {psychopy_rate:0.2f} Hz, Actual = {actual_rate:0.2f} Hz")

    if actual_rate < min_rate or  actual_rate > max_rate:
        raise InvalidWindowRefreshRate(_fps_error_msg(actual_rate, min_rate, max_rate))


def _fps_error_msg(actual_rate: float, min_rate: float, max_rate: float) -> str:
    return f"Actual rate ({actual_rate:0.2f} hz) is out of bounds: ({min_rate} to {max_rate})."


def make_win(
        full_screen=True,
        monitor_width=55,  # Width (cm) of viewable monitor area, used for psychopy sizing of UI
        subj_screendist_cm=60,  # Distance (cm) from subject head to middle of screen, used for psychopy sizing of UI
        screen_resolution=[1920,1080],  # Resolution of the screen in pixels, used for sizing the psychopy window
) -> visual.Window:
    custom_mon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=subj_screendist_cm
    )
    custom_mon.setSizePix(screen_resolution)
    custom_mon.saveMon()
    win = visual.Window(
        screen_resolution, fullscr=full_screen, monitor=custom_mon, units="pix", color=(0, 0, 0)
    )
    return win


def play_tone(freq = 1000, tone_duration = 0.2):
    """
        Plays a tone at 1000 hz, for 0.2 s, in two channel stereo mode
    """
    tone = sound.Sound(freq, tone_duration, stereo=True)
    tone.play()
    countdown(tone_duration + 0.02) # wait for 20 ms longer than tone_duration so tone can play fully


def change_win_color(win, color):
    win.color = color
    win.flip()


def create_text_screen(win, text, text_color: str = "white") -> visual.TextStim:
    screen = visual.TextStim(
        win=win,
        name="",
        text=text,
        font="Open Sans",
        pos=(0, 0),
        height=0.05,
        wrapWidth=800,
        ori=0.0,
        color=text_color,
        colorSpace="rgb",
        opacity=None,
        languageStyle="LTR",
        depth=0.0,
        units="height",
    )
    return screen


def present(
        win,
        screen,
        audio=None,
        wait_time=0,
        win_color=(0, 0, 0),
        waitKeys=True,
        first_screen=False,
        abort_keys: Optional[List] = None,  # Pass a list of abort keys ('q') if you want to make a task quit-able.
):
    win.color = win_color
    if screen is not None:
        screen.draw()
        win.flip()
        if first_screen:
            get_keys()
    if audio is not None:
        audio.play()
    countdown(wait_time, abort_keys)  # TODO: add abort keys back after debugging
    if waitKeys:
        get_keys()


def load_image(win: visual.Window, path: Union[str, os.PathLike]) -> visual.ImageStim:
    """
    Load the specified image and create an image stimulus.
    :param win: The PsychoPy window object the task will be displayed on.
    :param path: The name of the slide, including the extension
    :return: An image stimulus containing the requested slide
    """
    if not op.isfile(path):
        raise IOError(f'Required image file {path} does not exist')

    return visual.ImageStim(
        win,
        image=path,
        pos=(0, 0),
        units="deg",
    )


def load_slide(win: visual.Window, name: Union[str, os.PathLike]) -> visual.ImageStim:
    """
    Locate the specified image and create an image stimulus.
    :param win: The PsychoPy window object the task will be displayed on.
    :param name: The name of the slide, including the extension
    :return: An image stimulus containing the requested slide
    """
    slide_path = op.join(get_cfg_path('assets'), 'slides', name)
    return load_image(win, slide_path)


def load_video(win: visual.Window, path: Union[str, os.PathLike]) -> visual.MovieStim3:
    """
    Load the specified video and create a movie stimulus.
    :param win: The PsychoPy window object the task will be displayed on.
    :param path: The name of the countdown movie, including the extension
    :return: An image stimulus containing the requested countdown movie
    """
    if not op.isfile(path):
        raise IOError(f'Required video file {path} does not exist')

    return visual.MovieStim3(
        win=win,
        filename=path,
        noAudio=False,
    )


def load_countdown(win: visual.Window, name: Union[str, os.PathLike]) -> visual.MovieStim3:
    """
    Locate the specified countdown movie  and create a movie stimulus.
    :param win: The PsychoPy window object the task will be displayed on.
    :param name: The name of the countdown movie, including the extension
    :return: An image stimulus containing the requested countdown movie
    """
    video_path = op.join(get_cfg_path('assets'), 'countdown', name)
    return load_video(win, video_path)


def load_inter_task_slide(win: visual.Window) -> visual.ImageStim:
    """
    Returns ImageStim for slide that appears between tasks to inform subject of what is happening.
    Currently, the default is a slide that says "Thank you. Preparing next task"

    Parameters
    ----------
    win     The Psychopy Window object on which to display the slice
    """
    # TODO: Move the slide name to config if possible. This is made difficult by the fact that Tasks are reused
    #   across collections and the inter-task slide should really be dependent on the position in collection.
    return load_slide(win, "task_complete.png")


def delay(period: float) -> None:
    """
        Function which spins around doing nothing
        to stall time. Uses lsl local_clock
        which is accurate even below millisecond 
        range. Useful for waiting while something
        else is happening, or to stall a loop for
        a defined period of time.
        User defined time is specified by
        'period' in seconds
    """
    t1 = local_clock()
    t2 = t1
    while t2 - t1 < period:
        t2 = local_clock()


def countdown(period: float, abort_keys: Optional[List] = None) -> None:
    """
        Function to wait for a specified amount of time for a certain
        keypress - after which it simply times out
    """
    def get_abort_key(keyList=()):
        press = event.getKeys()
        if press:
            if not keyList:
                return press
            elif any([k in keyList for k in press]):
                return press
        return None

    t1 = local_clock()
    t2 = t1

    while t2 - t1 < period:
        if abort_keys is not None and abort_keys:
            if get_abort_key(abort_keys):
                return
        t2 = local_clock()


def get_keys(keyList=()):
    """
        Function to wait indefinitely until a certain key is pressed
    """
    event.clearEvents(eventType='keyboard')
    # Wait for keys checking every 5 ms
    while True:
        press = event.getKeys()
        if press:
            if not keyList:
                return press
            elif any([k in keyList for k in press]):
                return press
        delay(0.005)


def play_video(win, mov, wait_time=1, stop=True, keyList=None):
    clock = core.Clock()
    if mov.status == visual.FINISHED:
        win.flip()
        mov.seek(0)

    mov.play()
    while mov.status != visual.FINISHED:
        mov.draw()
        win.flip()
        if event.getKeys(keyList=keyList):
            if clock.getTime() < wait_time:
                continue
            if stop:
                mov.stop()
                mov.seek(0)
            else:
                mov.pause()
                mov.seek(0)
            break
