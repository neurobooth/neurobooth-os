# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:03 2021

@author: STM
"""

from psychopy import prefs
prefs.hardware['audioLib']=['pyo']
from psychopy.visual.textbox2 import TextBox2
from psychopy import sound, visual
import tasks.utils as utl


def my_textbox2(win, text, pos=(0,0), size=(None, None)):

    tbx = TextBox2(win, pos=pos, color='black', units='deg',lineSpacing=1,
                   letterHeight=1.2, text=text, font="Arial", size=size,
                   borderColor=None, fillColor=None, editable=False, alignment='center')
    return tbx
    
def welcome_screen():
    win = utl.make_win()
    
    welcome = visual.ImageStim(win, image= './tasks/NB1.jpg', units='pix')
    welcome_audio = sound.Sound('./tasks/welcome.wav', secs=-1, stereo=True, hamming=True,
            name='welcome_instructions')
            
    utl.present(win, welcome, welcome_audio, 5)
    
    win.winHandle.activate()
    return win


def finish_screen(win):
    
    finish = utl.create_text_screen(win,"Thanks for your participation\nAll task finished!")
    utl.present(win, finish, None, 10)
    win.close()
    return win
