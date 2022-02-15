# -*- coding: utf-8 -*-
"""
Created on Fri Jan 21 10:23:08 2022

@author: STM
"""


import random
import math
import time

from numpy import sqrt
from psychopy import core, visual, event, gui, data, sound, monitors
from psychopy.visual.textbox2 import TextBox2
from itertools import chain

from neurobooth_os.tasks import utils


class MOT():
    def __init__(self):
        # super().__init__(**kwargs)
        self.mycircle = {"x":[],       # circle x
                        "y":[],       # circle y
                        "d":[],       # circle motion direction in deg
                        "r":15,       # circle radius
                        "z":4,        # circle repulsion radius
                        "noise": 15,  # motion direction noise in deg
                        "speed": 2}  # circle speed in pixels/frame
        self.numCircles = 10        # total # of circles
        self.duration = 5        # desired duration of trial in s
        
        self.paperSize = 700        # size of stimulus graphics page
        self.clickTimeout = 15   # timeout for clicking on targets
        self.seed = 1               # URL parameter: if we want a particular random number generator seed

        self.win = visual.Window(
                [1920, 1080],
                fullscr=False,
                monitor=monitors.getAllMonitors()[1],
                units='pix',
                color= 'white'
                )
        
        self.trialCount = 0
        self.score = 0
        self.background = visual.Rect(self.win, width=self.paperSize, height=self.paperSize, fillColor='white', units='pix')
        self.trial_info_str = ''
    

    def trial_info_msg(self, msg_type= None):
        if msg_type == 'practice':
            msg = self.trial_info_str
        elif msg_type == 'test':
            msg = f" {self.trialCount} of 6. {self.trial_info_str}   Score {self.score}"
        else:
            msg = f" {self.trialCount} of 6. {' '*len(self.trial_info_str)}   Score {self.score}"
        return [visual.TextStim(self.win, text=msg, pos=(0, -10), units='deg', color='blue')]        
        
        
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
        
        
    # initialize the dots
    def setup(self, numCircles):
        
        # initialize start positions and motion directions randomly
        x, y, d = [], [], []
        for i in range(numCircles):
            x.append(random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"])
            y.append(random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"])
            d.append(random.random() * 2 * math.pi)
            
        self.mycircle["x"] = x
        self.mycircle["y"] = y
        self.mycircle["d"] = d
         
        # enforce proximity limits
        for i in range(numCircles -1):
            # reposition each circle until outside repulsion area of all other circles
            tooClose = True
            while tooClose:
            
                self.mycircle["x"][i] = random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"]
                self.mycircle["y"][i] = random.random() * (self.paperSize - 2.0 * self.mycircle["r"]) + self.mycircle["r"]
    
                # repulsion distance defaults to 5 times the circle's radius
                for j in range(i+1, numCircles):
                    dist = math.sqrt((self.mycircle["x"][i] - self.mycircle["x"][j])**2 + (self.mycircle["y"][i] - self.mycircle["y"][j])**2)
                    if dist > 5 * self.mycircle["r"]:
                        # print(i, j, dist)
                        tooClose = False
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
            newD = self.mycircle['d'][i] + random.random() * 2.0 * noise - noise
    
            # compute x and y shift
            velocityX = math.cos(newD) * self.mycircle['speed']
            velocityY = math.sin(newD) * self.mycircle['speed']
    
            # compute new x and y coordinates
            newX = oldX + velocityX
            newY = oldY + velocityY
    
            # avoid collisions
            for j in range(i, numCircles):
                # skip self
                if j == i: 
                    continue
    
                # look ahead one step: if next move collides, update direction til no collision or timeout            
                timeout = 0
                while timeout<1000:
                    timeout +=1
                    dist = math.sqrt((newX - self.mycircle['x'][j])**2 + (newY - self.mycircle['y'][j])**2)
    
                    if dist < repulsion:                
                        # update vector direction
                        newD += random.choice([-1,1]) * 0.05 * math.pi
                        # recompute  x shift and x coordinate
                        velocityX = math.cos(newD) * self.mycircle["speed"]
                        newX = oldX + velocityX
                        # recompute  y shift and y coordinate
                        velocityY = math.sin(newD) * self.mycircle["speed"]
                        newY = oldY + velocityY             
                    else:
                        break
                
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
        return circle
    
    
    
    
    def clickHandler(self, circle, n_targets, frame_type):
    
        # this handler listens for clicks on the targets
        # reveals correct and incorrect clicks
        # stops listening after numTargets clicks
        # gives feedback and paces the trial presentation
            
        mouse = event.Mouse(win=self.win)    
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
                        clicks.append([i, x, y, time_click])                        
                        n_clicks += 1                        
                        mouse.mouseClock = core.Clock()
                        if i < n_targets:
                            ncorrect += 1
                            c.color = 'green'
                            if frame_type == "test"
                                self.score += 1
                        else:
                            c.color = 'red'
                        if frame_type in ['test', 'practice']:
                            stim = circle + self.trial_info_msg(frame_type)
                        else:
                             stim = circle
                        self.present_stim(stim)
    
                        break
            prevButtonState = buttons
            
            if  rt > self.clickTimeout:
                rt = 'timeout'
                break
        
        return clicks, ncorrect, rt
                
    
        
        
    def showMovingDots(self, frame):

        
            
        numTargets = frame['n_targets']
        self.mycircle['speed'] = frame['speed']
        duration = frame['duration']
        frame_type = frame['type']    
        
        # set the random seed for each trial
        random.seed(frame['message'])
        
        circle = self.setup(frame['n_circles'])        
        circle = self.moveCircles(circle)
        
        if frame_type == 'test':
            self.present_stim(self.trial_info_msg())
        else:
            self.win.flip()
        
        # initialize the dots
        for n in range(numTargets):
            circle[n].color = 'green'
        if frame_type == 'test':
            self.present_stim(circle + self.trial_info_msg())
        else:
            self.present_stim(circle)
    
        core.wait(1)
    
        for n in range(numTargets):
            circle[n].color = 'black'

        clock  = core.Clock()
        while clock.getTime() < duration:
            circle = self.moveCircles(circle)
            # self.background.draw()
            if frame_type == 'test':
                self.present_stim(circle + self.trial_info_msg())
            else:
                self.present_stim(circle)
                
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
            elif frame['type'] == "test":
                self.trial_info_str = f"Click {frame['n_targets']} dots"
            else:
                circle = self.showMovingDots(frame)
                continue
            
            clockDuration = core.Clock()
            circle = self.showMovingDots(frame)
            trueDuration = round(clockDuration.getTime(), 2)
            
            msg_stim = self.trial_info_msg(frame['type'])
            self.present_stim(circle + msg_stim)
            
            clicks, ncorrect, rt =  self.clickHandler(circle, frame['n_targets'],  frame['type'])
            time.sleep(.5)
            
            state = 'click'                
            if rt == 'timeout':
                # rewind frame sequence by one frame, so same frame is displayed again
                frameSequence.insert(0, frame)
                
                msg_alert = "You took too long to respond!\n Remember: once the movement stops," +\
                                      "click the dots that flashed. \n" +\
                                      "Click continue to retry"
                msg_stim = self.my_textbox2(msg_alert)                
                self.present_stim([msg_stim], 'space')
                
                # set timout variable values
                state = 'timeout'
                rt = 0
                ncorrect = 0
                if frame['type'] == "test" and self.trialCount > 0:
                    self.trialCount -= 1
                    
            elif frame['type'] == 'practice':
                msg = f"You got {ncorrect} of {frame['n_targets']} dots correct. \nPress continue"
                if ncorrect < frame['n_targets']:
                    
                    if practiceErr < 2:  # up to 2 practice errors                    
                        # rewind frame sequence by one frame, so same frame is displayed again
                        frameSequence.insert(0, frame)
                        msg = "Let's try again. \nWhen the movement stops," +\
                            f"click the {frame['n_targets']} dots that flashed. \nPress continue"
                        
                        practiceErr += 1
                else:
                    practiceErr = 0
                msg_stim = self.my_textbox2(msg)
                self.present_stim([msg_stim], 'space')

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
    
          # we either save locally or to the server
    
    
    
    
    def setFrameSequence(self):
        testMessage ={            
            "begin":[self.my_textbox2("Multiple Object Tracking\n <img src=MOT.gif>")],
            "instruction1":[self.my_textbox2("Instructions: img src=happy-green-border.jpg> \n" +\
                            "Keep track of the dots that flash, \n they have green smiles behind them.")],
            "practice2":[self.my_textbox2(("<h2>Instructions:</h2>" 
                            "Next time, when the movement stops, "
                            "click the 2 dots that flashed.  "
                            "The other dots have "
                            "red sad faces behind them. "
                            "<img src=sad-red-border.jpg> "
                            "Try <b><i>not</i></b> to click on those.  "))],
            "practice3":[self.my_textbox2(("   Good!  "
                            "Now we'll do the same thing with "
                            "3 flashing dots.  "))],
            "targets3":[self.my_textbox2(("  Great! \n Now we'll do 6 more with 3 dots. "
                        "\nMotion is slow at first, then gets faster. "
                        "\nThis will be the first of 3 parts.  "
                        "\nWhen you lose track of dots, just guess. "
                        "\nYour score will be the total number of "
                        "\ngreen smiles that you click.  "))],
            "targets4":[self.my_textbox2((" Excellent!  "
                        "\nYou have finished the first part of this test. " 
                        "\nThere are two parts left.  " 
                        "\nThe next part has 4 flashing dots. "
                        "\nMotion is slow at first, then gets faster.  "
                        "\nWhen you lose track of dots, just guess. "
                        "\nEvery smile you click adds to your score!  "))],
            "targets5":[self.my_textbox2((" Outstanding!  "
                        "\nNow there is only one part left!  " 
                        "\nThe final part has 5 flashing dots! "
                        "\nMotion is slow at first, then gets faster.  "
                        "\nWhen you lose track of dots, just guess. "
                        "\nEvery smile you click adds to your score!  "))]
        }
    
        # set the random generator's seed
        s = self.seed;
    
        frame_type = [
            "begin",
            "message",
            "example",
            "message",
            "practice",
            "message",
            "practice"];
    
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
    
    
    def run(self):     
        frameSequence = self.setFrameSequence()
        self.run_trials(frameSequence)



mot = MOT()
mot.run()
# n_targets=2
# duration= 10

# circle, self.mycircle = setup(win, self.mycircle, numCircles, paperSize)
# background = visual.Rect(win, width=paperSize, height=paperSize, fillColor='white', units='pix')

# circle, self.mycircle = moveCircles(circle, self.mycircle)

# for n in range(n_targets):
#     circle[n].color = 'green'
# plot_dots(win, circle)

# for n in range(n_targets):
#     circle[n].color = 'black'
# core.wait(2)


# clock  = core.Clock()
# while clock.getTime() < duration:

#     circle, self.mycircle = moveCircles(circle, self.mycircle)
#     # background.draw()
#     plot_dots(win, circle)

# clicks, ncorrect =  clickHandler(circle, win, n_targets)
# for c in clicks:
#     ith_target = c[0]
#     color = 'green' if ith_target < n_targets else 'red'
#     circle[ith_target].color = color

# plot_dots(win, circle)

# core.wait(5)
# win.close()

