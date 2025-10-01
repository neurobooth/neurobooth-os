# -*- coding: utf-8 -*-
"""
Screens to be presented at the start and end of a session
"""
import neurobooth_os.tasks.utils as utl
from psychopy import visual, prefs

prefs.hardware["audioLib"] = ["pyo"]


def welcome_screen(win: visual.Window, slide: str) -> visual.Window:
    slide = utl.load_slide(win, slide)
    utl.present(win, slide, waitKeys=True, first_screen=True)
    win.winHandle.activate()
    return win


def finish_screen(win: visual.Window, slide: str) -> visual.Window:
    slide = utl.load_slide(win, slide)
    utl.present(win, slide, waitKeys=False)
    return win
