# -*- coding: utf-8 -*-
"""
Created on Tue Jul 20 10:00:03 2021

@author: STM
"""
import neurobooth_os.tasks.utils as utl
from psychopy import visual, prefs

prefs.hardware["audioLib"] = ["pyo"]


def welcome_screen(win: visual.Window) -> visual.Window:
    slide = utl.load_slide(win, 'welcome.jpg')
    utl.present(win, slide, waitKeys=True, first_screen=True)
    win.winHandle.activate()
    return win


def finish_screen(win: visual.Window) -> visual.Window:
    slide = utl.load_slide(win, 'end_slide_01_23_25.jpg')
    utl.present(win, slide, waitKeys=False)
    return win
