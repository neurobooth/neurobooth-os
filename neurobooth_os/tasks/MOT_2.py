

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
duration = 5000        # desired duration of trial in ms
paperSize = 500        # size of stimulus graphics page
clickTimeout = 15000   # timeout for clicking on targets
dots = 10              # URL parameter: if we want # of dots
seed = 1               # URL parameter: if we want a particular random number generator seed


# initialize the dots
def setup(win, mycircle, numCircles=10, paperSize=700):
    # initialize start positions and motion directions randomly
    for i in range(numCircles):
        mycircle["x"].append(random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"])
        mycircle["y"].append(random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"])
        mycircle["d"].append(random.random() * 2 * math.pi)

    # enforce proximity limits
    for i in range(1, numCircles):
        # reposition each circle until outside repulsion area of all other circles
        tooClose = True
        while tooClose:
        
            mycircle["x"][i] = random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"]
            mycircle["y"][i] = random.random() * (paperSize - 2.0 * mycircle["r"]) + mycircle["r"]

            # repulsion distance defaults to 5 times the circle's radius
            for j in range(i):
                dist = math.sqrt((mycircle["x"][i] - mycircle["x"][j])**2 + (mycircle["y"][i] - mycircle["y"][j])**2)
                if dist > 5 * mycircle["r"]:
                    print(dist)
                    tooClose = False
                    break

    # when done, update the circles on the DOM
    circle = []
    for i in range(numCircles):    
        circle.append(visual.Circle(win, mycircle["r"], pos=(mycircle["x"][i], mycircle["y"][i]), 
                                  lineColor='black', fillColor='black', units='pix'))
 
     # draw a box for the circles
    background = visual.Rect(win, width=paperSize, height=paperSize, fillColor='white', units='pix')

    return circle, mycircle, background


win = visual.Window(
        [900, 700],
        fullscr=False,
        monitor=monitors.getAllMonitors()[1],
        units='pix',
        color=(0, 0, 0)
        )

circle, mycircle, background = setup(win, mycircle, numCircles, paperSize)