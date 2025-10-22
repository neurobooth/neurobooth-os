#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import absolute_import, division
import json
import os
import os.path as op
from typing import Union

from psychopy import visual, core, data, event
from psychopy.constants import NOT_STARTED, STARTED, FINISHED

from neurobooth_os.tasks import utils, Task_Eyetracker, Task
from neurobooth_os.iout.stim_param_reader import get_cfg_path
import neurobooth_os


class hevelius_task(Task_Eyetracker):
    def __init__(
        self,
        record_psychopy=False,
        path="",
        subj_id="test",
        trial_data_fname="hevelius_centered_config.json",
        **kwargs,
    ):
        super().__init__(**kwargs)

        self.path_out = path
        self.subj_id = subj_id
        # Data file name stem = absolute path + name; later add .psyexp, .csv, .log, etc
        self.filename = self.path_out + f"{self.subj_id}_Hevelius_results"
        self.frameTolerance = 0.001  # how close to onset before 'same' frame
        self.rep = ""  # repeated task num to add to filename
        self.record_psychopy = record_psychopy

        self.trial_data_fpath = Task.asset_path(trial_data_fname, 'hevelius')
        with open(op.join(neurobooth_os.__path__[0], self.trial_data_fpath)) as f:
            self.trials_data = json.load(f)

    def convert_pix(self, loc, offset):
        newloc = [[], []]
        newloc[0] = int(loc[0] - offset["x"])
        newloc[1] = int(offset["y"] - loc[1])
        return newloc

    def run(self, prompt=False, last_Task=False, **kwarg):

        practice_blocks = sorted(
            list(
                filter(
                    lambda x: x.startswith("practice"), list(self.trials_data.keys())
                )
            )
        )
        trials_blocks = sorted(
            list(filter(lambda x: x.startswith("block"), list(self.trials_data.keys())))
        )

        utils.change_win_color(self.win, "grey")

        self.present_instructions(prompt)
        self.screen_text = visual.TextStim(
            win=self.win,
            name="",
            text="",
            font="Open Sans",
            pos=(-0.88, 0.5),
            height=0.03,
            wrapWidth=800,
            ori=0.0,
            color="black",
            colorSpace="rgb",
            opacity=None,
            languageStyle="LTR",
            depth=0.0,
            units="height",
            alignText="left",
            anchorHoriz="left",
            anchorVert="top",
        )

        self.run_blocks(practice_blocks, "Practice ")
        text_practice_done = 'Thank you for completing Practice Session \n\tPlease press:\n\t"Continue" to the task'
        continue_screen = utils.create_text_screen(self.win, text_practice_done)
        self.show_text(continue_screen, msg="Practice session completed")

        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        self.run_blocks(trials_blocks, "")
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True)

        if prompt:
            func_kwargs_func = {"prompt": prompt}
            self.rep += "_I"
            self.show_text(
                screen=self.task_end_screen,
                msg="Task-continue-repeat",
                func=self.run,
                func_kwargs=func_kwargs_func,
                waitKeys=False,
            )
        self.present_complete()
        return self.events

    def run_blocks(self, blocks, block_type):
        for index, block in enumerate(blocks):
            text_continue = (
                block_type
                + 'Block {} of {} \n\tPlease press:\n\t"Continue" to advance'.format(
                    index + 1, len(blocks)
                )
            )
            continue_screen = utils.create_text_screen(self.win, text_continue)
            self.show_text(
                continue_screen,
                msg=block_type + " Block {} of {}".format(index + 1, len(blocks)),
            )
            self.run_trials(self.trials_data[block], block_type)
            utils.change_win_color(self.win, "grey")

    def run_trials(self, block, block_type):
        utils.change_win_color(self.win, "white")
        # create a default keyboard (e.g. to check for escape)
        mouse = event.Mouse(win=self.win)

        # An ExperimentHandler isn't essential but helps with data saving
        thisExp = data.ExperimentHandler(
            name=self.subj_id,
            version="",
            runtimeInfo=None,
            originPath="C:\\neurobooth\\neurobooth-eel\\tasks\\hevelius_task.py",  # TODO: This is an old path!!!
            savePickle=False,
            saveWideText=False,
            dataFileName=self.filename + self.rep,
        )

        # Initialize components for Routine "trial"
        trialClock = core.Clock()
        polygon = visual.Circle(
            win=self.win,
            name="polygon",
            edges=32,
            radius=block["target_size"] / (2),
            ori=0,
            pos=(0, 0),
            units="pix",
            lineWidth=1,
            lineColor="black",
            lineColorSpace="rgb",
            fillColor="red",
            fillColorSpace="rgb",
            opacity=1,
            depth=0.0,
            interpolate=True,
        )

        x, y = [None, None]
        mouse.mouseClock = core.Clock()
        offset = block["offset"]
        locs = []
        for loc in block["target_positions"]:
            locs.append([loc["x"], loc["y"]])

        i = 0  # current index for locations

        # Create some handy timers
        routineTimer = (
            core.CountdownTimer()
        )  # to track time remaining of each (non-slip) routine

        # set up handler to look after randomisation of conditions etc
        trials = data.TrialHandler(
            nReps=len(locs),
            method="random",
            originPath=-1,
            trialList=[None],
            seed=None,
            name="trials",
        )

        thisExp.addLoop(trials)  # add the loop to the experiment
        thisTrial = trials.trialList[0]  # so we can initialise stimuli with some values
        # abbreviate parameter names if possible (e.g. rgb = thisTrial.rgb)
        if thisTrial is not None:
            for paramName in thisTrial:
                exec("{} = thisTrial[paramName]".format(paramName))

        for index, thisTrial in enumerate(trials):
            self.sendMessage(block_type + "Task {} of {}".format(index + 1, len(locs)))

            if "Practice" not in block_type:
                self.sendMessage(self.marker_trial_start)

            # abbreviate parameter names if possible (e.g. rgb = thisTrial.rgb)
            if thisTrial is not None:
                for paramName in thisTrial:
                    exec("{} = thisTrial[paramName]".format(paramName))

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
            currentLoc = self.convert_pix(locs[i], offset)
            polygon.pos = currentLoc
            self.send_target_loc(
                currentLoc, "target", to_marker=True, no_interpolation=1
            )

            # keep track of which components have finished
            trialComponents = [polygon, mouse]
            for thisComponent in trialComponents:
                thisComponent.tStart = None
                thisComponent.tStop = None
                thisComponent.tStartRefresh = None
                thisComponent.tStopRefresh = None
                if hasattr(thisComponent, "status"):
                    thisComponent.status = NOT_STARTED
            # reset timers
            t = 0
            _timeToFirstFrame = self.win.getFutureFlipTime(clock="now")
            trialClock.reset(-_timeToFirstFrame)  # t0 is time of first possible flip
            frameN = -1
            # -------Run Routine "trial"-------
            while continueRoutine:
                press = event.getKeys(keyList=["q"])
                if press:
                    polygon.setAutoDraw(False)
                    self.win.flip()
                    return
                # get current time
                t = trialClock.getTime()
                tThisFlip = self.win.getFutureFlipTime(clock=trialClock)
                tThisFlipGlobal = self.win.getFutureFlipTime(clock=None)
                frameN = (
                    frameN + 1
                )  # number of completed frames (so 0 is the first frame)

                # update/draw components on each frame

                # *polygon* updates
                if (
                    polygon.status == NOT_STARTED
                    and tThisFlip >= 0.0 - self.frameTolerance
                ):
                    # keep track of start time/frame for later
                    polygon.frameNStart = frameN  # exact frame index
                    polygon.tStart = t  # local t and not account for scr refresh
                    polygon.tStartRefresh = tThisFlipGlobal  # on global time
                    self.win.timeOnFlip(
                        polygon, "tStartRefresh"
                    )  # time at next scr refresh
                    polygon.setAutoDraw(True)
                    # MARKER Trial start 1
                # *mouse* updates
                if mouse.status == NOT_STARTED and t >= 0.0 - self.frameTolerance:
                    # keep track of start time/frame for later
                    mouse.frameNStart = frameN  # exact frame index
                    mouse.tStart = t  # local t and not account for scr refresh
                    mouse.tStartRefresh = tThisFlipGlobal  # on global time
                    self.win.timeOnFlip(
                        mouse, "tStartRefresh"
                    )  # time at next scr refresh
                    mouse.status = STARTED
                    mouse.mouseClock.reset()
                    prevButtonState = (
                        mouse.getPressed()
                    )  # if button is down already this ISN'T a new click

                if mouse.status == STARTED:  # only update if started and not finished!
                    x, y = mouse.getPos()
                    self.send_target_loc([x, y], "mouse", to_marker=False)
                    onTarget = 0
                    for obj in [polygon]:
                        if obj.contains(mouse):
                            onTarget = 1

                    self.sendMessage(
                        str(
                            {
                                "button": mouse.getPressed()[0],
                                "x": x,
                                "y": y,
                                "time": core.getTime(),
                                "in": onTarget,
                            }
                        )
                    )

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
                                self.sendMessage("mouse_valid_click")
                            else:
                                self.sendMessage("mouse_click")

                # check if all components have finished
                if (
                    not continueRoutine
                ):  # a component has requested a forced-end of Routine
                    break
                continueRoutine = (
                    False  # will revert to True if at least one component still running
                )
                for thisComponent in trialComponents:
                    if (
                        hasattr(thisComponent, "status")
                        and thisComponent.status != FINISHED
                    ):
                        continueRoutine = True
                        break  # at least one component has not yet finished

                # refresh the screen
                if (
                    continueRoutine
                ):  # don't flip if this routine is over or we'll get a blank screen
                    self.win.flip()

            # -------Ending Routine "trial"-------
            if "Practice" not in block_type:
                self.sendMessage(self.marker_trial_end)

            for thisComponent in trialComponents:
                if hasattr(thisComponent, "setAutoDraw"):
                    thisComponent.setAutoDraw(False)
                    # self.screen_text.setAutoDraw(False)
            trials.addData("polygon.started", polygon.tStartRefresh)
            trials.addData("polygon.stopped", polygon.tStopRefresh)
            # store data for trials (TrialHandler)
            if len(mouse.x):
                trials.addData("mouse.x", mouse.x[0])
            if len(mouse.y):
                trials.addData("mouse.y", mouse.y[0])
            if len(mouse.leftButton):
                trials.addData("mouse.leftButton", mouse.leftButton[0])
            if len(mouse.midButton):
                trials.addData("mouse.midButton", mouse.midButton[0])
            if len(mouse.rightButton):
                trials.addData("mouse.rightButton", mouse.rightButton[0])
            if len(mouse.time):
                trials.addData("mouse.time", mouse.time[0])
            if len(mouse.clicked_name):
                trials.addData("mouse.clicked_name", mouse.clicked_name[0])
            trials.addData("mouse.started", mouse.tStart)
            trials.addData("mouse.stopped", mouse.tStop)
            i += 1
            # the Routine "trial" was not non-slip safe, so reset the non-slip timer
            routineTimer.reset()
            thisExp.nextEntry()

        # these shouldn't be strictly necessary (should auto-save)
        if self.record_psychopy:
            thisExp.saveAsWideText(self.filename + self.rep + ".csv", delim="auto")
            thisExp.saveAsPickle(self.filename + self.rep)


if __name__ == "__main__":

    task = hevelius_task(
        record_psychopy=False, full_screen=False, blocks=2, num_iterations=2
    )
    task.run(prompt=True)
