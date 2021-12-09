#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division

import os

import numpy as np
from numpy.random import shuffle

from psychopy import visual, core, data, event, logging
from psychopy.constants import NOT_STARTED, STARTED, FINISHED
from psychopy.hardware import keyboard

from neurobooth_os.tasks.utils import make_win
from neurobooth_os.tasks import Task

class mouse_task(Task):

    def __init__(self, path="", subj_id="test", **kwargs):
        super().__init__(**kwargs)
        
        self.path_out = path
        self.subj_id = subj_id
        # Data file name stem = absolute path + name; later add .psyexp, .csv, .log, etc
        self.filename = self.path_out + f'{self.subj_id}_MouseTask_results'       
        self.frameTolerance = 0.001  # how close to onset before 'same' frame
        self.rep = ''  # repeated task num to add to filename


    def run(self, prompt=True, **kwargs):
        self.present_instructions(prompt)
        self.run_trials(prompt, **kwargs)
        self.present_complete()
        return self.events


    def run_trials(self, prompt, num_iterations=30, **kwargs):
        
        self.ntrials = num_iterations
        
        # create a default keyboard (e.g. to check for escape)
        defaultKeyboard = keyboard.Keyboard()
        mouse = event.Mouse(win=self.win)

        # An ExperimentHandler isn't essential but helps with data saving
        self.thisExp = data.ExperimentHandler(name="MouseTask", version='', runtimeInfo=None, savePickle=True,
                                              saveWideText=True, dataFileName=self.filename + self.rep) 

        # An ExperimentHandler isn't essential but helps with data saving
        thisExp = data.ExperimentHandler(name=self.subj_id, version='', runtimeInfo=None,
                                         originPath='C:\neurobooth\neurobooth-eel\tasks\\mouse.py',
                                         savePickle=True, saveWideText=True, dataFileName=self.filename + self.rep)
        
        # Initialize components for Routine "trial"
        trialClock = core.Clock()
        polygon = visual.Polygon(
            win=self.win, name='polygon',
            edges=9999, size=(30, 30),
            ori=0, pos=(0, 0), units='pix',
            lineWidth=1, lineColor='white', lineColorSpace='rgb',
            fillColor='white', fillColorSpace='rgb',
            opacity=1, depth=0.0, interpolate=True)

        x, y = [None, None]
        mouse.mouseClock = core.Clock()
        xLocs = [-.4, -.35, -.3, -.25, -.2, -.15, -.1, -.05, 0, 0.05, .1, .15, .2, .25, .3, .35, .4]
        yLocs = [-.4, -.35, -.3, -.25, -.2, -.15, -.1, -.05, 0, 0.05, .1, .15, .2, .25, .3, .35, .4]
        xLocs = [xLoc * 1920 for xLoc in xLocs]
        yLocs = [yLoc * 1080 for yLoc in yLocs]
        locs = []

        for x in xLocs:
            for y in yLocs:
                locs.append([x, y])

        # Shuffle the locations
        shuffle(locs)
        i = 0  # current index for locations
        mouse.setPos((locs[0][0], locs[0][1]))
        # Create some handy timers
        globalClock = core.Clock()  # to track the time since experiment started
        routineTimer = core.CountdownTimer()  # to track time remaining of each (non-slip) routine

        # set up handler to look after randomisation of conditions etc
        trials = data.TrialHandler(nReps=self.ntrials, method='random',
                                   originPath=-1,
                                   trialList=[None],
                                   seed=None, name='trials')
        
        thisExp.addLoop(trials)  # add the loop to the experiment
        thisTrial = trials.trialList[0]  # so we can initialise stimuli with some values
        # abbreviate parameter names if possible (e.g. rgb = thisTrial.rgb)
        if thisTrial is not None:
            for paramName in thisTrial:
                exec('{} = thisTrial[paramName]'.format(paramName))

        for thisTrial in trials:
            # abbreviate parameter names if possible (e.g. rgb = thisTrial.rgb)
            if thisTrial is not None:
                for paramName in thisTrial:
                    exec('{} = thisTrial[paramName]'.format(paramName))

            # ------Prepare to start Routine "trial"-------
            continueRoutine = True
            # update component parameters for each repeat
            # setup some python lists for storing info about the mouse
            mouse.x = []
            mouse.y = []
            mouse.leftButton = []
            mouse.midButton = []
            mouse.rightButton = []
            mouse.time = []
            mouse.clicked_name = []
            gotValidClick = False  # until a click is received
            currentLoc = locs[i]
            polygon.pos = currentLoc
            # keep track of which components have finished
            trialComponents = [polygon, mouse]
            for thisComponent in trialComponents:
                thisComponent.tStart = None
                thisComponent.tStop = None
                thisComponent.tStartRefresh = None
                thisComponent.tStopRefresh = None
                if hasattr(thisComponent, 'status'):
                    thisComponent.status = NOT_STARTED
            # reset timers
            t = 0
            _timeToFirstFrame = self.win.getFutureFlipTime(clock="now")
            trialClock.reset(-_timeToFirstFrame)  # t0 is time of first possible flip
            frameN = -1
            # -------Run Routine "trial"-------
            while continueRoutine:
                # get current time
                t = trialClock.getTime()
                tThisFlip = self.win.getFutureFlipTime(clock=trialClock)
                tThisFlipGlobal = self.win.getFutureFlipTime(clock=None)
                frameN = frameN + 1  # number of completed frames (so 0 is the first frame)

                # update/draw components on each frame

                # *polygon* updates
                if polygon.status == NOT_STARTED and tThisFlip >= 0.0 - self.frameTolerance:
                    # keep track of start time/frame for later
                    polygon.frameNStart = frameN  # exact frame index
                    polygon.tStart = t  # local t and not account for scr refresh
                    polygon.tStartRefresh = tThisFlipGlobal  # on global time
                    self.win.timeOnFlip(polygon, 'tStartRefresh')  # time at next scr refresh
                    polygon.setAutoDraw(True)
                    # MARKER Trial start 1
                # *mouse* updates
                if mouse.status == NOT_STARTED and t >= 0.0 - self.frameTolerance:
                    # keep track of start time/frame for later
                    mouse.frameNStart = frameN  # exact frame index
                    mouse.tStart = t  # local t and not account for scr refresh
                    mouse.tStartRefresh = tThisFlipGlobal  # on global time
                    self.win.timeOnFlip(mouse, 'tStartRefresh')  # time at next scr refresh
                    mouse.status = STARTED
                    mouse.mouseClock.reset()
                    prevButtonState = mouse.getPressed()  # if button is down already this ISN'T a new click

                if mouse.status == STARTED:  # only update if started and not finished!
                    x, y = mouse.getPos()
                    buttons = mouse.getPressed()
                    if buttons != prevButtonState:  # button state changed?
                        prevButtonState = buttons
                        if sum(buttons) > 0:  # state changed to a new click
                            # check if the mouse was inside our 'clickable' objects
                            gotValidClick = False
                            for obj in [polygon]:
                                if obj.contains(mouse):
                                    gotValidClick = True
                                    # MARKER RESPONSE 1
                                    mouse.clicked_name.append(obj.name)
                            x, y = mouse.getPos()
                            mouse.x.append(x)
                            mouse.y.append(y)
                            buttons = mouse.getPressed()
                            mouse.leftButton.append(buttons[0])
                            mouse.midButton.append(buttons[1])
                            mouse.rightButton.append(buttons[2])
                            mouse.time.append(mouse.mouseClock.getTime())
                            if gotValidClick:  # abort routine on response
                                continueRoutine = False

                # check if all components have finished
                if not continueRoutine:  # a component has requested a forced-end of Routine
                    break
                continueRoutine = False  # will revert to True if at least one component still running
                for thisComponent in trialComponents:
                    if hasattr(thisComponent, "status") and thisComponent.status != FINISHED:
                        continueRoutine = True
                        break  # at least one component has not yet finished

                # refresh the screen
                if continueRoutine:  # don't flip if this routine is over or we'll get a blank screen
                    self.win.flip()

            # -------Ending Routine "trial"-------
            for thisComponent in trialComponents:
                if hasattr(thisComponent, "setAutoDraw"):
                    thisComponent.setAutoDraw(False)
            trials.addData('polygon.started', polygon.tStartRefresh)
            trials.addData('polygon.stopped', polygon.tStopRefresh)
            # store data for trials (TrialHandler)
            if len(mouse.x):
                trials.addData('mouse.x', mouse.x[0])
            if len(mouse.y):
                trials.addData('mouse.y', mouse.y[0])
            if len(mouse.leftButton):
                trials.addData('mouse.leftButton', mouse.leftButton[0])
            if len(mouse.midButton):
                trials.addData('mouse.midButton', mouse.midButton[0])
            if len(mouse.rightButton):
                trials.addData('mouse.rightButton', mouse.rightButton[0])
            if len(mouse.time):
                trials.addData('mouse.time', mouse.time[0])
            if len(mouse.clicked_name):
                trials.addData('mouse.clicked_name', mouse.clicked_name[0])
            trials.addData('mouse.started', mouse.tStart)
            trials.addData('mouse.stopped', mouse.tStop)
            i += 1
            # the Routine "trial" was not non-slip safe, so reset the non-slip timer
            routineTimer.reset()
            thisExp.nextEntry()

        # these shouldn't be strictly necessary (should auto-save)
        thisExp.saveAsWideText(self.filename + self.rep + '.csv', delim='auto')
        thisExp.saveAsPickle(self.filename + self.rep)
    
        if prompt:
            func_kwargs = locals()
            func_kwargs_func = {'prompt': func_kwargs['prompt'],
                                'num_iterations': func_kwargs['num_iterations'] }
            self.rep += "_I"
            self.present_text(screen=self.press_task_screen, msg='task-continue-repeat', func=self.run_trials,
                          func_kwargs=func_kwargs_func, waitKeys=False)


if __name__ == "__main__":
    task = mouse_task(full_screen=False)
    task.run( prompt=True, num_iterations=30)

