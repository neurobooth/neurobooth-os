#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue May 25 08:44:11 2021

@author: adonay
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May 24 12:47:48 2021

@author: adonay
"""


#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar  9 14:55:50 2021

@author: adonay
"""

import random
import time
import numpy as np
from psychopy import core, visual, event
from psychopy.visual.textbox2 import TextBox2
from psychopy import iohub
from psychopy.iohub import launchHubServer
from psychopy.core import getTime
        # create psychopy window
win = visual.Window((1800, 1800), monitor='testMonitor', allowGUI=True, color='white')

io = launchHubServer()
keyboard = io.devices.keyboard
out = keyboard.getReleases(keys='1')

print(out)

[-2.6]
[-2.2, 0, 2.2]
stim = [
    TextBox2(win, pos=(0, 9), color='black', units='deg', letterHeight=1.2,
             text=f"press <b>press</b> " +
             "when you see this symbol",
             font="arial", lineSpacing=.7,
             borderColor=None, fillColor=None,
             editable=False
             ),

    visual.ImageStim(win, image=f"DSC/images/1.gif", pos=(0, 6), units='deg'),  # , size=7),
    visual.ImageStim(win, image='DSC/images/key.png', pos=(0, 0), units='deg'),  # , size=15),
    visual.Rect(win, units='deg', pos=(2.2, -2.6),
                lineColor='red', size=(2.5, 2.5),
                lineWidth=4)]


response_events_old = keyboard.getReleases()
for ss in stim:
    ss.draw()
win.flip()
response_events = keyboard.waitForReleases(maxWait=3000.0, keys=['1', '2', '3'])
print(response_events)


win = visual.Window((1800, 1800), monitor='testMonitor', allowGUI=True, color='white')

stim = [
    TextBox2(
        win,
        pos=(
            0,
            9),
        color='black',
        units='deg',
        letterHeight=2.2,
        lineSpacing=.7,
        size=(
            20,
            None),
        text=f"press <b>press</b> when you see this symbol, press <b>press</b> when you see this symbol",
        font="Cairo",
        borderColor=None,
        fillColor=None,
        editable=False,
        alignment='right',
        anchor="center"),
]

for ss in stim:
    ss.draw()
win.flip()

win.close()
