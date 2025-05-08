# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:23 2021

@author: STM
"""

from __future__ import absolute_import, division

from typing import List, Optional

from psychopy import core, event, monitors

import time
import os.path as op

from pylsl import local_clock
from psychopy import visual

text_continue_repeat = (
        'Please press:\n\t"Continue" to advance' + '\n\t"Repeat" to go back'
)
text_continue = 'Please press:\n\t"Continue" to advance'
text_practice_screen = "Please practice the task \n\tPress any button when done"
text_task = "Please do the task \n\tPress any button when done"
text_end = "Thank you. You have completed this task"


def change_win_color(win, color):
    win.color = color
    win.flip()


def send_marker(marker, msg):
    marker.push_sample([f"{msg}_{time.time()}"])


def make_win(
        full_screen=True,
        monitor_width=55,
        subj_screendist_cm=60,
        # in centimeters from subject head to middle of the screen in our setup. The eye tracker distance measured is from head to center of eye tracker
):
    mon = monitors.getAllMonitors()[0]
    custom_mon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=subj_screendist_cm
    )

    mon_size = monitors.Monitor(mon).getSizePix()
    custom_mon.setSizePix(mon_size)
    custom_mon.saveMon()
    win = visual.Window(
        mon_size, fullscr=full_screen, monitor=custom_mon, units="pix", color=(0, 0, 0)
    )
    print("Monitor Set Refresh Rate:{:.2f} Hz".format(1 / win.monitorFramePeriod))
    actual_frame_rate = win.getActualFrameRate(
        nIdentical=30, nMaxFrames=300, nWarmUpFrames=10, threshold=1
    )
    if actual_frame_rate is None:
        raise RuntimeError("Window returned 'None' instead of frame rate.")

    print(
        "Monitor Actual Refresh Rate:{:.2f} Hz".format(actual_frame_rate)
    )
    return win


def change_win_color(win, color):
    win.color = color
    win.flip()


def create_text_screen(win, text):
    screen = visual.TextStim(
        win=win,
        name="",
        text=text,
        font="Open Sans",
        pos=(0, 0),
        height=0.05,
        wrapWidth=800,
        ori=0.0,
        color="white",
        colorSpace="rgb",
        opacity=None,
        languageStyle="LTR",
        depth=0.0,
        units="height",
    )
    return screen


def create_image_screen(win, path_image, pos=(0, 0)):
    screen = visual.ImageStim(win, image=path_image, pos=pos, units="deg")
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


def get_end_screen(win, root_pckg):
    """
    Parameters
    ----------
    win
    root_pckg

    Returns
    -------
        screen "Preparing next task" shown between tasks
    """
    task_complete_img = op.join(root_pckg, "tasks", "assets", "task_complete.png")
    if not op.isfile(task_complete_img):
        raise IOError(f'Required image file {task_complete_img} does not exist')

    end_screen = visual.ImageStim(
        win,
        image=task_complete_img,
        pos=(0, 0),
        units="deg",
    )
    return end_screen


def countdown(period: float, abort_keys: Optional[List] = None) -> None:

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

    def delay(period: float) -> None:
        t1 = local_clock()
        t2 = t1
        while t2 - t1 < period:
            t2 = local_clock()

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



def play_video(win, mov, wait_time=1, stop=True):
    clock = core.Clock()
    if mov.status == visual.FINISHED:
        win.flip()
        mov.seek(0)

    mov.play()
    while mov.status != visual.FINISHED:
        mov.draw()
        win.flip()
        if event.getKeys():
            if clock.getTime() < wait_time:
                continue
            if stop:
                mov.stop()
                mov.seek(0)
            else:
                mov.pause()
                mov.seek(0)
            break


def rewind_video(win, mov):
    key = get_keys(keyList=["space", "r"])
    if key == ["space"]:
        mov.stop()
        return False
    elif key == ["r"]:
        win.color = [0, 0, 0]
        win.flip()
        mov.seek(0)
        return True


def advance():
    key = get_keys(keyList=["space"])
    if key == ["space"]:
        return True


def run_task(task, prompt=True):
    print("starting task")
    task.present_instructions(prompt)
    print("starting instructions")
    task.present_practice(prompt)
    print("starting task")
    task.present_task(prompt)
    print("end screen")
    task.present_complete()
    print("close window")
    task.close()
    print("task done")