# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:03 2021

@author: STM
"""

from psychopy import prefs
prefs.hardware['audioLib']=['pyo']
from psychopy.visual.textbox2 import TextBox2
from psychopy import sound, visual, event
import tasks.utils as utl


def my_textbox2(win, text, pos=(0,0), size=(None, None)):

    tbx = TextBox2(win, pos=pos, color='black', units='deg',lineSpacing=1,
                   letterHeight=1.2, text=text, font="Arial", size=size,
                   borderColor=None, fillColor=None, editable=False, alignment='center')
    return tbx
    
def welcome_screen(with_audio=True, win=None):
    if win is None:
        win = utl.make_win(full_screen=False)
    
    welcome = visual.ImageStim(win, image= './tasks/NB1.jpg', units='pix')
    if with_audio:
        welcome_audio = sound.Sound('./tasks/welcome.wav', secs=-1, stereo=True, hamming=True,
                                    name='welcome_instructions')
    else:
        welcome_audio = None
    utl.present(win, welcome, welcome_audio, 5, waitKeys=True, first_screen=True)
    
    win.winHandle.activate()
    return win


def finish_screen(win):
    
    
    finish = visual.ImageStim(win, './tasks/NB2.jpg', units='pix')
    utl.present(win, finish, None, 2)
    win.close()
    return win
