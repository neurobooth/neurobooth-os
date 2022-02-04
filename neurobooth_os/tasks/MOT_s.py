# -*- coding: utf-8 -*-
"""
Created on Fri Jan 21 10:23:08 2022

@author: STM
"""


import random
import math

from numpy import sqrt
from psychopy import core, visual, event, gui, data, sound, monitors
from itertools import chain

from neurobooth_os.tasks import utils

mycircle = {"x":[],       # circle x
            "y":[],       # circle y
            "d":[],       # circle motion direction in deg
            "r":15,       # circle radius
            "z":4,        # circle repulsion radius
            "noise": 15,  # motion direction noise in deg
            "speed": 2}  # circle speed in pixels/frame
numCircles = 10        # total # of circles
numTargets = 4         # # of targets to track
duration = 20        # desired duration of trial in s
paperSize = 700        # size of stimulus graphics page
clickTimeout = 15   # timeout for clicking on targets

seed = 1               # URL parameter: if we want a particular random number generator seed


# initialize the dots
def setup(win, mycircle, numCircles=10, paperSize=700):
    # initialize start positions and motion directions randomly
    for i in range(numCircles):
        mycircle["x"].append(random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"])
        mycircle["y"].append(random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"])
        mycircle["d"].append(random.random() * 2 * math.pi)

    # enforce proximity limits
    for i in range(numCircles -1):
        # reposition each circle until outside repulsion area of all other circles
        tooClose = True
        while tooClose:
        
            mycircle["x"][i] = random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"]
            mycircle["y"][i] = random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"]

            # repulsion distance defaults to 5 times the circle's radius
            for j in range(i+1, numCircles):
                dist = math.sqrt((mycircle["x"][i] - mycircle["x"][j])**2 + (mycircle["y"][i] - mycircle["y"][j])**2)
                if dist > 5 * mycircle["r"]:
                    # print(i, j, dist)
                    tooClose = False
                    break

    # when done, update the circles on the DOM
    circle = []
    for i in range(numCircles):    
        circle.append(visual.Circle(win, mycircle["r"], pos=(mycircle["x"][i], mycircle["y"][i]), 
                                  lineColor='black', fillColor='black', units='pix'))
 
    return circle, mycircle

def moveCircles(circle, mycircle):
    """Update the position of the circles for the next frame
    - add noise to the velocity vector
    - bounce circles off elastic boundaries
    - avoid collisions b/w circles
    all computations are done outside the DOM

    Returns
    -------
    """

    timeout = 0
    noise = (mycircle["noise"] * math.pi) / 180  # angle to rad
    repulsion = mycircle["z"] * mycircle["r"]

    for i in range(numCircles):
        # save the current dot's coordinates
        oldX = mycircle['x'][i]
        oldY = mycircle['y'][i]

        # update direction vector with noise
        newD = mycircle['d'][i] + random.random() * 2.0 * noise - noise

        # compute x and y shift
        velocityX = math.cos(newD) * mycircle['speed']
        velocityY = math.sin(newD) * mycircle['speed']

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
                dist = math.sqrt((newX - mycircle['x'][j])**2 + (newY - mycircle['y'][j])**2)

                if dist < repulsion:                
                    # update vector direction
                    newD += random.choice([-1,1]) * 0.05 * math.pi
                    # recompute  x shift and x coordinate
                    velocityX = math.cos(newD) * mycircle["speed"]
                    newX = oldX + velocityX
                    # recompute  y shift and y coordinate
                    velocityY = math.sin(newD) * mycircle["speed"]
                    newY = oldY + velocityY             
                else:
                    break
            
        # enforce elastic boundaries
        if newX >= (paperSize - mycircle["r"]) or newX <= mycircle["r"]:
            # bounce off left or right boundaries
            velocityX *= -1  # invert x component of velocity vector
            newX = oldX + velocityX  # recompute new x coordinate
        
        if newY >= (paperSize - mycircle["r"]) or newY <= mycircle["r"]:
            # bounce off top or bottom boundaries
            velocityY *= -1  # invert y component of velocity vector
            newY = oldY + velocityY  # recompute new y coordinate
        
        # assign new coordinates to each circle
        mycircle['x'][i] = newX
        mycircle['y'][i] = newY

        # compute final vector direction
        # use atan2 (not atan)!
        mycircle['d'][i] = math.atan2(velocityY, velocityX)

        # now we update the DOM elements
        circle[i].pos = [ newX - paperSize//2, newY - paperSize//2]
        circle[i].draw()
    win.flip()
    return circle, mycircle


def showMovingDots(frame, circle, mycircle, background):
    
    motionTimer = 0
    motionIterations = 0
    
    # set the random seed for each trial
    random.seed(frame.message)
    # initialize the dots
    



def clickHandler(circle, win, n_targets=2):

    # this handler listens for clicks on the targets
    # reveals correct and incorrect clicks
    # stops listening after numTargets clicks
    # gives feedback and paces the trial presentation

    
    mouse = event.Mouse(win=win)    
    mouse.mouseClock = core.Clock()    
    mouse.clickReset()   
                  
    n_clicks, prevButtonState = 0, None
    clicks, clicked =[], []    
    while n_clicks < n_targets:
        mouse.clickReset()
        buttons, time = mouse.getPressed(getTime=True)
        
        if sum(buttons) > 0 and buttons != prevButtonState:
            for i, c in enumerate(circle):
                if mouse.isPressedIn(c):
                    # Check not clicked on previous circle
                    if i in [clk[0] for clk in clicks]:
                        continue
                    x, y = mouse.getPos()                    
                    clicks.append([i, x, y])
                    print(i, x, y)
                    n_clicks += 1
                    c.color = 'yellow' 
                    plot_dots(win, circle)
                    break
        prevButtonState = buttons
    return clicks
            
            
def plot_dots(win, circle):        
    for c in circle:
        c.draw()
    win.flip()


# def in_circle(mouse_x, mouse_y):
#     # -- Return boolean value depending on mouse position, if it is in circle or not
#     if math.sqrt(((mouse_x - self.x) ** 2) + ((mouse_y - self.y) ** 2)) < self.radius:
#         return True
#     else:
#         return False

win = visual.Window(
        [1920, 1080],
        fullscr=True,
        monitor=monitors.getAllMonitors()[1],
        units='pix',
        color=(0, 0, 0)
        )

n_targets=2
duration= 10

circle, mycircle = setup(win, mycircle, numCircles, paperSize)
background = visual.Rect(win, width=paperSize, height=paperSize, fillColor='white', units='pix')

circle, mycircle = moveCircles(circle, mycircle)
for n in range(n_targets):
    circle[n].color = 'green'
plot_dots(win, circle)

for n in range(n_targets):
    circle[n].color = 'black'
core.wait(2)


clock  = core.Clock()
while clock.getTime() < duration:

    circle, mycircle = moveCircles(circle, mycircle)
    # background.draw()
    plot_dots(win, circle)

clicks =  clickHandler(circle, win, n_targets)
for c in clicks:
    ith_target = c[0]
    color = 'green' if ith_target < n_targets else 'red'
    circle[ith_target].color = color

plot_dots(win, circle)

core.wait(5)
win.close()

