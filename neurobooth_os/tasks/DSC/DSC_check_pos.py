# -*- coding: utf-8 -*-
"""
Created on Fri Jan 14 09:56:25 2022

@author: STM
"""

# -*- coding: utf-8 -*-
"""
Created on Tue Nov 16 14:07:20 2021

@author: Adonay Nunes
"""

import os.path as op
import random
import time
from datetime import datetime
import numpy as np
import pandas as pd

from psychopy import core, visual, event, iohub
from psychopy.iohub import launchHubServer
from psychopy.visual.textbox2 import TextBox2

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task


def my_textbox2(win, text, pos=(0, 0), size=(None, None)):
    tbx = TextBox2(win, pos=pos, color='black', units='deg', lineSpacing=.9,
                   letterHeight=1, text=text, font="Arial",  # size=(20, None),
                   borderColor=None, fillColor=None, editable=False, alignment='center')
    return tbx


def present_msg(elems, win):
    for e in elems:
        e.draw()
    win.flip()



from psychopy import sound, core, event, monitors, visual, monitors

monitor_width=55 
monitor_distance=50
mon = monitors.getAllMonitors()[0]
customMon = monitors.Monitor('demoMon', width=monitor_width, distance=monitor_distance)
win = visual.Window(
    [1920, 1080],   
    fullscr=False,  
    monitor=customMon,
    units='pix',    
    color='white'
    )

rootdir = op.join(neurobooth_os.__path__[0], 'tasks', 'DSC')

kpos = [-5, 0, 5]
rec_xpos = kpos[3- 1]
stim = [
    visual.ImageStim(win, image=op.join(rootdir, f'images/1.gif'), pos=(0, 10), units='deg'),
    visual.ImageStim(win, image= op.join(rootdir, 'images/key.png'), pos=(0, 0), units='deg'),
    visual.Rect(win, units='deg', lineColor='red', pos=(rec_xpos, -5.5), size=(3.5, 3.5), lineWidth=4),
    my_textbox2(win,"You should press 1 on the keyboard when you see this symbol", (0, -9)),
    visual.ImageStim(win, image= op.join(rootdir, 'continue.png'), pos=(0, 0), units='deg')
    ]
                     
present_msg(stim, win)
win.color = 'white'

