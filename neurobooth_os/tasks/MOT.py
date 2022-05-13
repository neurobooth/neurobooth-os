# -*- coding: utf-8 -*-
"""
Created on Fri Jan 21 10:23:08 2022

@author: STM
"""

import os.path as op
import random
import math
import time

from numpy import sqrt
import pandas as pd
from psychopy import core, visual, event
from psychopy.visual.textbox2 import TextBox2
from itertools import chain

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task_Eyetracker


class MOT(Task_Eyetracker):
    def __init__(self, path="", subj_id="test", task_name="MOT", duration=90, **kwargs):
        super().__init__(**kwargs)
        
        self.path_out = path
        self.task_name = task_name
        self.subj_id = subj_id
        self.mycircle = {"x":[],       # circle x
                        "y":[],       # circle y
                        "d":[],       # circle motion direction in deg
                        "r":15,       # circle radius
                        "z":4,        # circle repulsion radius
                        "noise": 15,  # motion direction noise in deg
                        "speed": 2}  # circle speed in pixels/frame
        self.numCircles = 10        # total # of circles
        self.duration = 5        # desired duration of trial in s
        
        self.paperSize = 500        # size of stimulus graphics page
        self.clickTimeout = 10   # timeout for clicking on targets
        self.seed = 2               # URL parameter: if we want a particular random number generator seed
        self.trialCount = 0
        self.score = 0        
        self.trial_info_str = ''
        self.rootdir = op.join(neurobooth_os.__path__[0], 'tasks', 'MOT')
        
        self.setup(self.win)
        

        
    def setup(self, win):

        self.win.color = "white"
        self.win.flip()
        self.background = [visual.Rect(self.win, width=self.paperSize, height=self.paperSize, lineColor='black', fillColor='white', units='pix')]
        # create the trials chain
        self.frameSequence = self.setFrameSequence()
        
    def trial_info_msg(self, msg_type= None):
        if msg_type == 'practice':
            msg = self.trial_info_str
        elif msg_type == 'test':
            msg = f" {self.trialCount + 1} of 6. {self.trial_info_str}   Score {self.score}"
        else:
            msg = f" {self.trialCount + 1} of 6. {' '*len(self.trial_info_str)}   Score {self.score}"
        return [visual.TextStim(self.win, text=msg, pos=(0, -8), units='deg', color='blue')]        
        
        
    def my_textbox2(self, text, pos=(0, 0), size=(None, None)):
        tbx = TextBox2(self.win, pos=pos, color='black', units='deg', lineSpacing=.9,
                        letterHeight=1, text=text, font="Arial",  # size=(20, None),
                        borderColor=None, fillColor=None, editable=False, alignment='center')
        return tbx
        
    
    def present_stim(self, elems,  key_resp=None):
        for e in elems:
            e.draw()
        self.win.flip()
        if key_resp is not None:
            event.waitKeys(keyList=key_resp)
    
        
    def run(self, prompt=True, last_task=False, subj_id='test', **kwargs):
        self.subj_id = subj_id   
        self.present_instructions(prompt) 
        self.win.color = "white"
        self.win.flip()
        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True) 
        self.run_trials(self.frameSequence)
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True) 
        self.present_complete(last_task)
        return self.events
    
    
    # initialize the dots
    def setup_dots(self, numCircles):
        
        # initialize start positions and motion directions randomly
        x, y, d = [], [], []
        for i in range(numCircles):
            x.append(random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"])
            y.append(random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"])
            d.append(random.random() * 2 * math.pi)
            
        self.mycircle["x"] = x
        self.mycircle["y"] = y
        self.mycircle["d"] = d
        repulsion = self.mycircle["z"] * self.mycircle["r"]
        # enforce proximity limits
        for i in range(1, numCircles -1):
            # reposition each circle until outside repulsion area of all other circles
            tooClose = True
            while tooClose:
            
                self.mycircle["x"][i] = random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"]
                self.mycircle["y"][i] = random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"]
    
                # repulsion distance defaults to 5 times the circle's radius
                tooClose = False
                for j in range(i):
                    if i == j:
                        continue
                    dist = math.sqrt((self.mycircle["x"][i] - self.mycircle["x"][j])**2 + (self.mycircle["y"][i] - self.mycircle["y"][j])**2)
                    if dist < ( 5 * self.mycircle["r"]):
                        # print(i, j, dist)
                        tooClose = True
                        break
    
        # when done, update the circles on the DOM
        circle = []
        for i in range(numCircles):    
            circle.append(visual.Circle(self.win, self.mycircle["r"], pos=(self.mycircle["x"][i], self.mycircle["y"][i]), 
                                      lineColor='black', fillColor='black', units='pix'))
     
        return circle
    
    def moveCircles(self, circle):
        """Update the position of the circles for the next frame
        - add noise to the velocity vector
        - bounce circles off elastic boundaries
        - avoid collisions b/w circles
        all computations are done outside the DOM
    
        Returns
        -------
        """
    
        timeout = 0
        noise = (self.mycircle["noise"] * math.pi) / 180  # angle to rad
        repulsion = self.mycircle["z"] * self.mycircle["r"]
        
        numCircles = len(self.mycircle['x'])
        for i in range(numCircles):
            # save the current dot's coordinates
            oldX = self.mycircle['x'][i]
            oldY = self.mycircle['y'][i]
    
            # update direction vector with noise
            newD = self.mycircle['d'][i] + random.uniform(0, 1) * 2.0 * noise - noise
    
            # compute x and y shift
            velocityX = math.cos(newD) * self.mycircle['speed']
            velocityY = math.sin(newD) * self.mycircle['speed']
    
            # compute new x and y coordinates
            newX = oldX + velocityX
            newY = oldY + velocityY
    
            # avoid collisions
            for j in range(numCircles):#i, numCircles):
                # skip self
                if j == i: 
                    continue
    
                # look ahead one step: if next move collides, update direction til no collision or timeout            
                timeout = 0
                while timeout < 1000:
                    timeout +=1
                    dist = math.sqrt((newX - self.mycircle['x'][j])**2 + (newY - self.mycircle['y'][j])**2)
    
                    if dist < repulsion:                
                        # update vector direction
                        newD += random.choice([-1,1]) * random.uniform(0, 1) * math.pi
                        # recompute  x shift and x coordinate
                        velocityX = math.cos(newD) * self.mycircle["speed"]                        
                        # recompute  y shift and y coordinate
                        velocityY = math.sin(newD) * self.mycircle["speed"]
                        if dist < math.sqrt(((oldX + velocityX )- self.mycircle['x'][j])**2 + ((oldY + velocityY)  - self.mycircle['y'][j])**2):
                            newX = oldX + velocityX
                            newY = oldY + velocityY             
                    else:
                        break
                    if timeout == 10000:
                        print(f'time out {j} {i} d = {dist}')
                        
            # enforce elastic boundaries
            if newX >= (self.paperSize - self.mycircle["r"]) or newX <= self.mycircle["r"]:
                # bounce off left or right boundaries
                velocityX *= -1  # invert x component of velocity vector
                newX = oldX + velocityX  # recompute new x coordinate
            
            if newY >= (self.paperSize - self.mycircle["r"]) or newY <= self.mycircle["r"]:
                # bounce off top or bottom boundaries
                velocityY *= -1  # invert y component of velocity vector
                newY = oldY + velocityY  # recompute new y coordinate
            
            # assign new coordinates to each circle
            self.mycircle['x'][i] = newX
            self.mycircle['y'][i] = newY
    
            # compute final vector direction
            # use atan2 (not atan)!
            self.mycircle['d'][i] = math.atan2(velocityY, velocityX)
    
            # now we update the DOM elements
            circle[i].pos = [ newX - self.paperSize//2, newY - self.paperSize//2]
            circle[i].draw()
            self.send_target_loc(circle[i].pos, target_name=f"target_{i}")
        return circle
    
    
    def clickHandler(self, circle, n_targets, frame_type):
    
        # this handler listens for clicks on the targets
        # reveals correct and incorrect clicks
        # stops listening after numTargets clicks
        # gives feedback and paces the trial presentation
            
        mouse = event.Mouse(win=self.win)
        self.Mouse.setVisible(1)
        mouse.mouseClock = core.Clock()    
        mouse.clickReset()   
        trialClock = core.Clock()
        
        n_clicks, prevButtonState = 0, None
        clicks, ncorrect =[], 0    
        while n_clicks < n_targets:
            mouse.clickReset()
            buttons, time_click = mouse.getPressed(getTime=True)
            rt = trialClock.getTime()
            
            if sum(buttons) > 0 and buttons != prevButtonState:
                for i, c in enumerate(circle):
                    if mouse.isPressedIn(c):
                        # Check not clicked on previous circle
                        if i in [clk[0] for clk in clicks]:
                            continue
                        x, y = mouse.getPos()  
                        self.sendMessage(self.marker_response_start)                  
                        clicks.append([i, x, y, time_click])                        
                        n_clicks += 1                        
                        mouse.mouseClock = core.Clock()
                        if i < n_targets:
                            ncorrect += 1
                            c.color = 'green'
                            if frame_type == "test":
                                self.score += 1
                        else:
                            c.color = 'red'
                        if frame_type in ['test', 'practice']:
                            stim = circle + self.trial_info_msg(frame_type)
                        else:
                             stim = circle
                        self.present_stim(self.background + stim)
    
                        break
            prevButtonState = buttons
            
            if  rt > self.clickTimeout:
                rt = 'timeout'
                break
        self.Mouse.setVisible(0)
        return clicks, ncorrect, rt
                
    
        
        
    def showMovingDots(self, frame):

        numTargets = frame['n_targets']
        self.mycircle['speed'] = frame['speed']
        duration = frame['duration']
        frame_type = frame['type']    
        
        # set the random seed for each trial
        random.seed(frame['message'])
        
        circle = self.setup_dots(frame['n_circles'])        
        circle = self.moveCircles(circle)
        
        if frame_type == 'test':
            self.present_stim(self.trial_info_msg())
        else:
            self.win.flip()
        
        # initialize the dots, flashgreen colors
        countDown = core.CountdownTimer()
        countDown.add(1.5)

        while countDown.getTime() > 0:
            for n in range(numTargets):
                circle[n].color = 'green'
            if frame_type == 'test':
                self.present_stim(self.background + circle + self.trial_info_msg())
            else:
                self.present_stim(self.background + circle)        
            core.wait(.1)

            for n in range(numTargets):
                circle[n].color = 'black'
                
            if frame_type == 'test':
                self.present_stim(self.background + circle + self.trial_info_msg())
            else:
                self.present_stim(self.background + circle)
            core.wait(.1)

        clock  = core.Clock()
        while clock.getTime() < duration:
            circle = self.moveCircles(circle)
            if frame_type == 'test':
                self.present_stim(self.background + circle + self.trial_info_msg())
            else:
                self.present_stim(self.background + circle)
                
        return  circle
        
        
    def run_trials(self, frameSequence):
        results = []

        total = 0
        practiceErr = 0
        while len(frameSequence):
            # read the frame sequence one frame at a time
            frame = frameSequence.pop(0)
    
            # check if it's the startup frame
            if frame["type"] in ["begin", "message"]:                
                self.present_stim(frame["message"], "space")
                continue
            
            # else show the animation               
            if self.trialCount == 6:
                self.trialCount = 0
            
            if frame['type'] == "practice":
                self.trial_info_str = f"Click the {frame['n_targets']} dots that were green"
                self.sendMessage(self.marker_practice_trial_start)
                self.sendMessage(f"number targets:{frame['n_targets']}") 
                
            elif frame['type'] == "test":
                self.trial_info_str = f"Click {frame['n_targets']} dots"
                self.sendMessage(self.marker_trial_start)
                self.sendMessage(f"number targets:{frame['n_targets']}") 
            else:
                circle = self.showMovingDots(frame)
                continue
            
            clockDuration = core.Clock()
            circle = self.showMovingDots(frame)
            trueDuration = round(clockDuration.getTime(), 2)
            
            msg_stim = self.trial_info_msg(frame['type'])
            self.present_stim(self.background + circle + msg_stim)
            
            clicks, ncorrect, rt =  self.clickHandler(circle, frame['n_targets'],  frame['type'])
            
            if frame['type'] == "test":
                self.sendMessage(self.marker_trial_end)
            elif frame['type'] == "practice":
                self.sendMessage(self.marker_practice_trial_end)
                
            time.sleep(.5)
            
            state = 'click'                
            if rt == 'timeout':
                # rewind frame sequence by one frame, so same frame is displayed again
                frameSequence.insert(0, frame)
                
                msg_alert = "You took too long to respond!\nRemember: once the movement stops,\n" +\
                                      "click the dots that flashed." 
                msg_stim = self.my_textbox2(msg_alert)                
                self.present_stim([self.continue_msg, msg_stim], 'space')
                
                # set timout variable values
                state = 'timeout'
                rt = 0
                ncorrect = 0
                if frame['type'] == "test" and self.trialCount > 0:
                    self.trialCount -= 1
                    
            elif frame['type'] == 'practice':
                msg = f"You got {ncorrect} of {frame['n_targets']} dots correct."
                if ncorrect < frame['n_targets']:
                    
                    if practiceErr < 2:  # up to 2 practice errors                    
                        # rewind frame sequence by one frame, so same frame is displayed again
                        frameSequence.insert(0, frame)
                        msg = "Let's try again. \nWhen the movement stops," +\
                            f"click the {frame['n_targets']} dots that flashed."
                        
                        practiceErr += 1
                else:
                    practiceErr = 0
                msg_stim = self.my_textbox2(msg)
                self.present_stim([self.continue_msg,  msg_stim], 'space')

            frame['rt'] = rt
            frame["ncorrect"] = ncorrect
            frame["clicks"] = clicks
            frame['trueDuration'] = trueDuration
            
            if frame['type'] == "test":
                total += frame['n_targets']
            
            results.append(
                {
                    "type": frame['type'], # one of practice or test
                    "hits": ncorrect,
                    "rt": rt,
                    "numTargets": frame['n_targets'],
                    "numdots": frame['n_circles'],
                    "speed": self.mycircle['speed'],
                    "noise": self.mycircle['noise'],
                    "duration": trueDuration,
                    "state": state,
                    'seed': frame['message']
                })
            
            if frame['type'] == "test":
                self.trialCount += 1
    
        # the sequence is empty, we are done!
    
        rtTotal = [r['rt'] for r in results if r["type"]=='practice' and r['state']!='timeout']
        
        outcomes = {}
        outcomes["score"] = self.score
        outcomes["correct"] = round(self.score / total, 3)
        outcomes["rtTotal"] = round(sum(rtTotal), 1)
    
        # SAVE RESULTS to file
        df_res = pd.DataFrame(results)
        df_out = pd.DataFrame.from_dict(outcomes, orient='index', columns=['vals'])
        res_fname = f'{self.subj_id}_{self.task_name}_results.csv'
        out_fname = f'{self.subj_id}_{self.task_name}_outcomes.csv'
        df_res.to_csv(self.path_out + res_fname)
        df_out.to_csv(self.path_out + out_fname)
        self.task_files = '{' + f"{res_fname}, {out_fname}" + '}'
        
        
    
    def setFrameSequence(self):
        testMessage ={            
            "begin": [ visual.ImageStim(self.win, image=op.join(self.rootdir, 'intro.png'), pos=(0, 0), units='deg') ],
            "instruction1":[ visual.ImageStim(self.win, image=op.join(self.rootdir, 'inst1.png'), pos=(0, 0), units='deg') ],
            "practice2": [ visual.ImageStim(self.win, image=op.join(self.rootdir, 'inst2.png'), pos=(0, 0), units='deg') ],
            "practice3": [ visual.ImageStim(self.win, image=op.join(self.rootdir, 'inst3.png'), pos=(0, 0), units='deg') ],
            "targets3": [ visual.ImageStim(self.win, image=op.join(self.rootdir, 'targ3.png'), pos=(0, 0), units='deg') ],
            "targets4": [ visual.ImageStim(self.win, image=op.join(self.rootdir, 'targ4.png'), pos=(0, 0), units='deg') ],
            "targets5": [ visual.ImageStim(self.win, image=op.join(self.rootdir, 'targ5.png'), pos=(0, 0), units='deg') ],
        }
        self.continue_msg = visual.ImageStim(self.win, image=op.join(self.rootdir, 'continue.png'), pos=(0, 0), units='deg')
        
        # set the random generator's seed
        s = self.seed
    
        frame_type = [
            "begin",
            "message",
            "example",
            "message",
            "practice",
            "message",
            "practice"]
    
        frame_message = [
            testMessage["begin"],
            testMessage["instruction1"],
            "example1",
            testMessage["practice2"],
            "practice1",
            testMessage["practice3"],
            "practice2"];
    
        frame_ntargets = [0,0,2,0,2,0,3]
        frame_speed = [0,0,0.5,0,0.5,0,0.5]
        frameSequence = []
        # instructions and practice phase
        for i in range(len(frame_type)):            
            frameSequence.append(
                    {
                        "type": frame_type[i],
                        "n_targets": frame_ntargets[i],
                        "n_circles": self.numCircles,
                        "speed": frame_speed[i],
                        "duration": 3,
                        "message": frame_message[i]
                    })
        
        # test 3 dots
        frame_type = ["message","test","test","test","test","test","test"]
        frame_message = [testMessage["targets3"],s, s+1, s+2, s+3, s+4, s+5,s+6]

        frame_speed = [0,1,2,3,4,5,6]
        for i in range(len(frame_type)):            
            frameSequence.append(
                    {
                        "type": frame_type[i],
                        "n_targets": 3,
                        "n_circles": self.numCircles,
                        "speed": frame_speed[i],
                        "duration": self.duration,
                        "message": frame_message[i]
                    })
    
        # test 4 dots
        frame_message = [testMessage["targets4"],s+10, s+11, s+12, s+13, s+14, s+15,s+16]
        for i in range(len(frame_type)):            
            frameSequence.append(
                    {
                        "type": frame_type[i],
                        "n_targets": 4,
                        "n_circles": self.numCircles,
                        "speed": frame_speed[i],
                        "duration": self.duration,
                        "message": frame_message[i]
                    })
    
        # test 5 dots
        frame_message = [testMessage["targets5"],s+20, s+21, s+22, s+23, s+24, s+25,s+26]
        for i in range(len(frame_type)):            
            frameSequence.append(
                    {
                        "type": frame_type[i],
                        "n_targets": 5,
                        "n_circles": self.numCircles,
                        "speed": frame_speed[i],
                        "duration": self.duration,
                        "message": frame_message[i]
                    })
        return frameSequence
    
    
