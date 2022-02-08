# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:23 2021

@author: STM
"""

from __future__ import absolute_import, division
from psychopy import core, event, monitors

import time
import os.path as op

from psychopy import visual
from psychopy import prefs
prefs.hardware['audioLib'] = ['pyo']


text_continue_repeat = 'Please press:\n\t"Continue" to advance' + \
                '\n\t"Repeat" to go back'
text_continue = 'Please press:\n\t"Continue" to advance'
text_practice_screen = 'Please practice the task \n\tPress any button when done'
text_task='Please do the task \n\tPress any button when done'
text_end='Thank you. You have completed this task'

def change_win_color(win, color):
    win.color = color
    win.flip()

def send_marker(marker, msg):
    marker.push_sample([f"{msg}_{time.time()}"])

def make_win(full_screen=True, monitor_width=55, monitor_distance=60):
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor('demoMon', width=monitor_width, distance=monitor_distance)

    mon_size = monitors.Monitor(mon).getSizePix()
    customMon.setSizePix(mon_size)
    customMon.saveMon()
    win = visual.Window(
        mon_size,
        fullscr=full_screen,
        monitor=customMon,
        units='pix',
        color=(0, 0, 0)
        )
    print("Monitor Set Refresh Rate:{:.2f} Hz".format(1/win.monitorFramePeriod))
    print("Monitor Actual Refresh Rate:{:.2f} Hz".format(win.getActualFrameRate(nIdentical=30, nMaxFrames=300,
                                                                                nWarmUpFrames=10, threshold=1)))
    return win

def change_win_color(win, color):
    win.color = color
    win.flip()

def create_text_screen(win, text):
    screen = visual.TextStim(win=win, name='',
                             text=text,
                             font='Open Sans',
                             pos=(0, 0),
                             height=0.05,
                             wrapWidth=800,
                             ori=0.0,
                             color='white',
                             colorSpace='rgb',
                             opacity=None,
                             languageStyle='LTR',
                             depth=0.0,
                             units='height')
    return screen


def create_image_screen(win, path_image, pos=(0,0)):
    screen = visual.ImageStim(win, image=path_image, pos=pos,units='deg')
    return screen


def present(win, screen, audio=None, wait_time=0, win_color=(0, 0, 0), waitKeys=True, first_screen=False):
    win.color = win_color
    if screen is not None:
        screen.draw()
        win.flip()
        if first_screen:
            event.waitKeys()
    if audio is not None:
        audio.play()
    core.wait(wait_time)
    if waitKeys:
        event.waitKeys()


def play_video(win, mov, wait_time=1, stop=True):
    clock  = core.Clock()
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
            else:
                mov.pause()
            break

def rewind_video(win, mov):
    key = event.waitKeys(keyList=['space', 'r'])
    if key == ["space"]:
        mov.stop()
        return False
    elif key == ['r']:
        win.color = [0, 0, 0]
        win.flip()
        mov.seek(0)
        return True

def repeat_advance():
    key = event.waitKeys(keyList=['space', 'r'])
    if key == ["space"]:
        return False
    elif key == ['r']:
        return True

def advance():
    key = event.waitKeys(keyList=['space'])
    if key == ["space"]:
        return True

def run_task(task, prompt=True):
    print('starting task')
    task.present_instructions(prompt)
    print('starting instructions')
    task.present_practice(prompt)
    print('starting task')
    task.present_task(prompt)
    print('end screen')
    task.present_complete()
    print('close window')
    task.close()
    print('task done')

