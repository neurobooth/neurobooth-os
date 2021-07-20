# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:23 2021

@author: STM
"""

from __future__ import absolute_import, division
import os.path as op
from psychopy import visual
from psychopy import prefs
prefs.hardware['audioLib']=['pyo']
from psychopy import sound, core, event, monitors, visual
import time

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
                             depth=0.0)
    return screen


def present(win, screen, audio, wait_time, win_color=(0, 0, 0)):
    if screen is not None:
        screen.draw()
        win.flip()
    if audio is not None:
        audio.play()
    core.wait(wait_time)
    event.waitKeys()
    win.color = win_color
    win.flip()

def play_video(win, mov):
    mov.play()
    while mov.status != visual.FINISHED:
        mov.draw()
        win.flip()
        if event.getKeys():
            break

def make_win(monitor_width=55, monitor_distance=50):    
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor('demoMon', width=monitor_width, distance=monitor_distance)
    mon_size = monitors.Monitor(mon).getSizePix()
    win = visual.Window(mon_size, fullscr=False, monitor=customMon, units='pix', color='white')
    return win

# win = visual.Window(
#     size=(SCN_W, SCN_H), fullscr=full_screen, screen=0,
#     winType='pyglet', allowGUI=True, allowStencil=False,
#     monitor='testMonitor', color=[0,0,0], colorSpace='rgb',
#     blendMode='avg', useFBO=True, 
#     units='height')

    