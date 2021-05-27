#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division

from psychopy import visual, core, data, event, logging
from psychopy.constants import NOT_STARTED, STARTED, FINISHED
from numpy.random import shuffle
import os

from psychopy.hardware import keyboard




def mouse_task():
    # Store info about the experiment session
    psychopyVersion = '2020.2.3' # psychopy.__version__
    expName = 'mouse'  # from the Builder filename that created this script
    expInfo = {'participant': '', 'session': '001'}
    expInfo['date'] = data.getDateStr()  # add a simple timestamp
    expInfo['expName'] = expName
    expInfo['psychopyVersion'] = psychopyVersion
    
    # Data file name stem = absolute path + name; later add .psyexp, .csv, .log, etc
    filename = "C:\\neurobooth\\neurobooth-eel"+ os.sep + u'data/%s_%s_%s' % (expInfo['participant'], expName, expInfo['date'])
    
    # An ExperimentHandler isn't essential but helps with data saving
    thisExp = data.ExperimentHandler(name=expName, version='',
        extraInfo=expInfo, runtimeInfo=None,
        originPath='C:\neurobooth\neurobooth-eel\tasks\mouse.py',
        savePickle=True, saveWideText=True,
        dataFileName=filename)
    # save a log file for detail verbose info
    logFile = logging.LogFile(filename+'.log', level=logging.EXP)
    logging.console.setLevel(logging.WARNING)  # this outputs to the screen, not a file
    
    endExpNow = False  # flag for 'escape' or other condition => quit the exp
    frameTolerance = 0.001  # how close to onset before 'same' frame
    
    
    # Start Code - component code to be run before the window creation
    
    # Setup the Window
    win = visual.Window(
        size=[1920, 1080], fullscr=False, screen=0, 
        winType='pyglet', allowGUI=True, allowStencil=False,
        monitor='testMonitor', color=[0,0,0], colorSpace='rgb',
        blendMode='avg', useFBO=True, 
        units='height')
    # store frame rate of monitor if we can measure it
    expInfo['frameRate'] = win.getActualFrameRate()
    if expInfo['frameRate'] != None:
        frameDur = 1.0 / round(expInfo['frameRate'])
    else:
        frameDur = 1.0 / 60.0  # could not measure, so guess
    
    # create a default keyboard (e.g. to check for escape)
    defaultKeyboard = keyboard.Keyboard()
    mouse = event.Mouse(win=win)
    text = visual.TextStim(win=win, name='text',
        text='You will see series of red dots\n\nYour task is to click on the red dot\n\nclick to Continue',
        font='Arial',
        pos=(0, 0), height=0.05, wrapWidth=None, ori=0,
        color='white', colorSpace='rgb', opacity=1,
        languageStyle='LTR',
        depth=0.0)
    text.setAutoDraw(True)
    win.flip()
    buttons = [0, 0, 0]
    while buttons != [1, 0, 0]:
        buttons, times = mouse.getPressed(getTime=True)
    
    text.setAutoDraw(False)
    
    # Initialize components for Routine "trial"
    trialClock = core.Clock()
    polygon = visual.Polygon(
        win=win, name='polygon',
        edges=9999, size=(0.05, 0.05),
        ori=0, pos=(0, 0),
        lineWidth=1, lineColor='red', lineColorSpace='rgb',
        fillColor='red', fillColorSpace='rgb',
        opacity=1, depth=0.0, interpolate=True)
    
    x, y = [None, None]
    mouse.mouseClock = core.Clock()
    xLocs = [-.4, -.35, -.3, -.25, -.2, -.15, -.1, -.05, 0, 0.05, .1, .15, .2, .25, .3, .35, .4]
    yLocs = [-.4, -.35, -.3, -.25, -.2, -.15, -.1, -.05, 0, 0.05, .1, .15, .2, .25, .3, .35, .4]
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
    trials = data.TrialHandler(nReps=50, method='random', 
        extraInfo=expInfo, originPath=-1,
        trialList=[None],
        seed=None, name='trials')
    thisExp.addLoop(trials)  # add the loop to the experiment
    thisTrial = trials.trialList[0]  # so we can initialise stimuli with some values
    # abbreviate parameter names if possible (e.g. rgb = thisTrial.rgb)
    if thisTrial != None:
        for paramName in thisTrial:
            exec('{} = thisTrial[paramName]'.format(paramName))
    
    for thisTrial in trials:
        currentLoop = trials
        # abbreviate parameter names if possible (e.g. rgb = thisTrial.rgb)
        if thisTrial != None:
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
        _timeToFirstFrame = win.getFutureFlipTime(clock="now")
        trialClock.reset(-_timeToFirstFrame)  # t0 is time of first possible flip
        frameN = -1
        # -------Run Routine "trial"-------
        while continueRoutine:
            # get current time
            t = trialClock.getTime()
            tThisFlip = win.getFutureFlipTime(clock=trialClock)
            tThisFlipGlobal = win.getFutureFlipTime(clock=None)
            frameN = frameN + 1  # number of completed frames (so 0 is the first frame)
    
            # update/draw components on each frame
            
            # *polygon* updates
            if polygon.status == NOT_STARTED and tThisFlip >= 0.0-frameTolerance:
                # keep track of start time/frame for later
                polygon.frameNStart = frameN  # exact frame index
                polygon.tStart = t  # local t and not account for scr refresh
                polygon.tStartRefresh = tThisFlipGlobal  # on global time
                win.timeOnFlip(polygon, 'tStartRefresh')  # time at next scr refresh
                polygon.setAutoDraw(True)
            # *mouse* updates
            if mouse.status == NOT_STARTED and t >= 0.0-frameTolerance:
                # keep track of start time/frame for later
                mouse.frameNStart = frameN  # exact frame index
                mouse.tStart = t  # local t and not account for scr refresh
                mouse.tStartRefresh = tThisFlipGlobal  # on global time
                win.timeOnFlip(mouse, 'tStartRefresh')  # time at next scr refresh
                mouse.status = STARTED
                mouse.mouseClock.reset()
                prevButtonState = mouse.getPressed()  # if button is down already this ISN'T a new click
            if mouse.status == STARTED:  # only update if started and not finished!
                x, y = mouse.getPos()
                print(x, y, mouse.mouseClock.getTime())
                buttons = mouse.getPressed()
                if buttons != prevButtonState:  # button state changed?
                    prevButtonState = buttons
                    if sum(buttons) > 0:  # state changed to a new click
                        # check if the mouse was inside our 'clickable' objects
                        gotValidClick = False
                        for obj in [polygon]:
                            if obj.contains(mouse):
                                gotValidClick = True
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
            
            # check for quit (typically the Esc key)
            if endExpNow or defaultKeyboard.getKeys(keyList=["escape"]):
                core.quit()
            
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
                win.flip()
        
        # -------Ending Routine "trial"-------
        for thisComponent in trialComponents:
            if hasattr(thisComponent, "setAutoDraw"):
                thisComponent.setAutoDraw(False)
        trials.addData('polygon.started', polygon.tStartRefresh)
        trials.addData('polygon.stopped', polygon.tStopRefresh)
        # store data for trials (TrialHandler)
        if len(mouse.x): trials.addData('mouse.x', mouse.x[0])
        if len(mouse.y): trials.addData('mouse.y', mouse.y[0])
        if len(mouse.leftButton): trials.addData('mouse.leftButton', mouse.leftButton[0])
        if len(mouse.midButton): trials.addData('mouse.midButton', mouse.midButton[0])
        if len(mouse.rightButton): trials.addData('mouse.rightButton', mouse.rightButton[0])
        if len(mouse.time): trials.addData('mouse.time', mouse.time[0])
        if len(mouse.clicked_name): trials.addData('mouse.clicked_name', mouse.clicked_name[0])
        trials.addData('mouse.started', mouse.tStart)
        trials.addData('mouse.stopped', mouse.tStop)
        i += 1 
        # the Routine "trial" was not non-slip safe, so reset the non-slip timer
        routineTimer.reset()
        thisExp.nextEntry()
        
    # completed 50 repeats of 'trials'
    
    text = visual.TextStim(win=win, name='text',
        text='Thank you for your participation',
        font='Arial',
        pos=(0, 0), height=0.05, wrapWidth=None, ori=0,
        color='white', colorSpace='rgb', opacity=1,
        languageStyle='LTR',
        depth=0.0)
    text.setAutoDraw(True)
    win.flip()
    core.wait(3)
    text.setAutoDraw(False)
    # Flip one final time so any remaining win.callOnFlip() 
    # and win.timeOnFlip() tasks get executed before quitting
    win.flip()
    
    
    # these shouldn't be strictly necessary (should auto-save)
    thisExp.saveAsWideText(filename+'.csv', delim='auto')
    thisExp.saveAsPickle(filename)
    logging.flush()
    # make sure everything is closed down
    thisExp.abort()  # or data files will save again on exit
    win.close()
    # core.quit()
# mouse_task()