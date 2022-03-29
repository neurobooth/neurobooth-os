# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:03 2021

@author: STM
"""
import os.path as op

import neurobooth_os
import neurobooth_os.tasks.utils as utl
from psychopy import sound, visual, event
from psychopy.visual.textbox2 import TextBox2
from psychopy import prefs
prefs.hardware['audioLib'] = ['pyo']


def my_textbox2(win, text, pos=(0, 0), size=(None, None)):

    tbx = TextBox2(win, pos=pos, color='black', units='deg', lineSpacing=1,
                   letterHeight=1.2, text=text, font="Arial", size=size,
                   borderColor=None, fillColor=None, editable=False, alignment='center')
    return tbx


def welcome_screen(with_audio=True, win=None):
    if win is None:
        win = utl.make_win(full_screen=False)

    fname = op.join(neurobooth_os.__path__[0], 'tasks/assets/welcome.jpg')
    welcome = visual.ImageStim(win, image=fname, units='pix')
    if with_audio:
        fname = op.join(neurobooth_os.__path__[0], 'tasks/assets/welcome.wav')
        welcome_audio = sound.Sound(fname, secs=-1, stereo=True, hamming=True,
                                    name='welcome_instructions')
    else:
        welcome_audio = None
    utl.present(win, welcome, welcome_audio, 0, waitKeys=True, first_screen=True)

    win.winHandle.activate()
    return win


def finish_screen(win):
    fname = op.join(neurobooth_os.__path__[0], 'tasks/assets/end_slide_3_7_22.jpg')
    finish = visual.ImageStim(win, fname, units='pix')
    utl.present(win, finish, waitKeys=False)
    return win
