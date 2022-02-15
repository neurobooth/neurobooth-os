
    # <meta name="description" content="Multiple Object Tracking">
    # <meta name="copyright" content="2014 The Many Brains Project, Inc.">
    # <meta name="author" content="Paolo Martini">
   

    #  version = "March 2018  Ver. 1.4 "

#      URL parameters:

#         debug=true        : output trial by trial information to console
#         showresults=true  : opens a new window to copy results, with button to save CSV file on local disk
#         autosave=true     : save data to file automatically
#         filename=test.csv : filename to save data to
#         demo=true         : runs in demo mode (only one trial per block)
#         dots=#dots        : number of total dots for all trials (minimum 6)
#         seed=#            : random number generator seed
#         help              : show usage

#      Usage: MOTTest.html?debug=true
#             MOTTest.html?showresults=true
#             MOTTest.html?debug=true&showresults=true
#             MOTTest.html?dots=10
#             MOTTest.html?seed=31
#             MOTTest.html?help
# -->
import random
import math

from numpy import sqrt
from psychopy import core, visual, event, gui, data, sound
from random import randint, sample, choice, shuffle
from itertools import chain
import os, csv

circle = []         # Array of SVG circles objects
happy =[]              # array of happy targets
sad = []               # array of sad targets
mycircle = {"x":[],       # circle x
            "y":[],       # circle y
            "d":[],       # circle motion direction in deg
            "r":15,       # circle radius
            "z":4,        # circle repulsion radius
            "noise": 15,  # motion direction noise in deg
            "speed": 2}  # circle speed in pixels/frame
numCircles = 10        # total # of circles
numTargets = 4         # # of targets to track
targets = []           # array indicating whether targets are clicked
clicks = 0             # # of clicks
targetClicks = 0       # # of clicked targets
duration = 5000        # desired duration of trial in ms
trueDuration = None           # measured duration of trial in ms
frametime = 0          # measured display frame duration in ms
paper = None                   # stimulus graphics page
paperSize = 500        # size of stimulus graphics page
timeoutRef = None              # reference to the click timeout trap
clickTimeout = 15000   # timeout for clicking on targets
frameSequence = []     # object containing the sequence of frames and their properties
frame = None                   # single frame object
timestamp = None               # used for timing
rt = None                      # reaction time
practiceErr = 0        # practice errors counter
trialCount = 0         # trial counter
results = []           # to store trials details and responses
outcomes = {}          # object containing outcome variables
score=0                # cumulative correct hits
total=0                # max possible score
debug = None                   # URL parameter: output to console
showresults = None             # URL parameter: if we want to show results in a popup window and save to file
autosave = None                # URL parameter: if they want to save data in a file automatically
filename = None                # URL parameter: filename for data
demo = False           # URL parameter: if we want a quick demo run (only 1 trial per block)
dots = 10              # URL parameter: if we want # of dots
seed = 1               # URL parameter: if we want a particular random number generator seed
usage= ""              # URL parameter: show usage

        # output a message and execute an action
        function showAlert(alertMessage,alertButtonText,action,timeout)
        {
            # set the message to display
            getID('alertText').innerHTML = alertMessage;

            # if args contain button text,
            # show the button and set the required action for it,
            # otherwise hide the button
            if(alertButtonText && !timeout)
            {
                getID('alertButton').style.width='15em';
                getID('alertButton').style.margin='0 auto';
                getID('alertButton').style.display='block';
                getID('alertButton').innerHTML = alertButtonText;
                getID('alertButton').onclick = action;
                showCursor("document.body");
            }
            else getID('alertButton').style.display='none';

            # if args contain a timeout,
            # trigger the action automatically when timeout expires
            if(timeout) setTimeout(action,timeout);

            showFrame('alertBox');
        }

        # log results to console
        function logResults()
        {
            if(!results[0]) return;

            log = '', propertyName, len = results.length;
            if(len === 1)
            {
                for (propertyName in results[0])
                {
                    if(results[0].hasOwnProperty(propertyName))
                        log += propertyName+' ';
                }
                console.log(log);
                log= '';
            }
            for (propertyName in results[len-1])
            {
                if (results[len-1].hasOwnProperty(propertyName))
                    log += (results[len-1][propertyName] + ' ');
            }
            console.log(log);
        }

# initialize the dots
def setup():
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
    for i in range(numCircles):    
        circle[i] = visual.Circle(self.win, mycircle["r"], pos=(mycircle["x"][i], mycircle["y"][i]), 
                                  lineColor=self.color, fillColor=self.color, units='pix')
 
     # draw a box for the circles
    background = visual.Rect(self.win, width=700, height=700, fillColor='white', units='pix')

    

def moveCircles():
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

    for(i = 0; i < numCircles; i++)
        # save the current dot's coordinates
        oldX = mycircle['x'][i]
        oldY = mycircle['y'][i]

        # update direction vector with noise
        newD = mycircle['d'][i] + random.random() * 2.0 * noise - noise

        # compute x and y shift
        velocityX = math.cos(newD) * mycircle['speed']
        velocityY = math.sin(newD) * mycircle['speed']

        # compute new x and y coordinates
        newX = oldX + velocityX;
        newY = oldY + velocityY;

        # avoid collisions
        for j in range(numCircles):
            # skip self
            if j === i: continue

            # look ahead one step: if next move collides, update direction til no collision or timeout
            tooClose = True
            timeout = 0
            while tooClose and timeout < 100:
                timeout +=1
                dist = math.sqrt((newX - mycircle['x'][j])**2 + (newY - mycircle['y'][j])**2)

                if dist <= repulsion:                
                    # update vector direction
                    newD += random.choice([-1,1]) * 0.05 * math.pi
                    # recompute  x shift and x coordinate
                    velocityX = math.cos(newD) * mycircle["speed"]
                    newX = oldX + velocityX
                    # recompute  y shift and y coordinate
                    velocityY = math.sin(newD) * mycircle["speed"]
                    newY = oldY + velocityY             
                else:
                     tooClose = False
            
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
        circle[i].node.setAttribute("cx", newX);
        circle[i].node.setAttribute("cy", newY);
  



def ShowTargets():
    # move the happy green smileys to the coordinates
    # of the targets, make them visible and hide the dots
    for in range(numTargets):
        happy[i].attr({"x": circle[i].attr("cx") - mycircle.r, "y": circle[i].attr("cy") - mycircle.r})
        happy[i].node.style.display = "block"
        circle[i].node.style.display = "none"


def HideTargets():
    # make the dots visible and hide the smileys
    for in range(numTargets):
        happy[i].node.style.display = "none";
        circle[i].node.style.display = "block"





def clickHandler():

    # this handler listens for clicks on the targets
    # reveals correct and incorrect clicks
    # stops listening after numTargets clicks
    # gives feedback and paces the trial presentation

  
    
    mouse = event.Mouse(win=win)
    # retrieve the identity of this dot
    index = this.data("index")

    # increment the clicks counter
    clicks++;

    # mark correct as green
    if index < numTargets:
    
        happy[index].attr({"x": circle[index].attr("cx")-mycircle.r,
                           "y": circle[index].attr("cy")-mycircle.r})
        happy[index].node.style.display = "block"
        circle[index].node.style.display = "none"
        #circle[index].attr({fill: "chartreuse"});

        # check they are not clicking on an already clicked target
        if targets[index] === 0:        
            targets[index] = 1
            targetClicks++

            if (frame.type === "test"):            
                # update the score
                score++
                getID("textRight").innerHTML = "Score "+score
    
    # mark wrong as red
    else
    
        sad[index].attr({"x": circle[index].attr("cx")-mycircle.r,
                         "y": circle[index].attr("cy")-mycircle.r})
        sad[index].node.style.display = "block"
        circle[index].node.style.display = "none"
    

    # check if we got enough clicks
    if clicks === numTargets:
    
        rt = timestamp
        timestamp = now()
        rt = timestamp - rt

        # clear the click timeout trap
        clearTimeout(timeoutRef)

        # disable the click handlers
        for(i = 0; i < numCircles; i++) circle[i].unclick()

        # push this trial in the results record
        results.append(
        {
            "type": frame.type, # one of practice or test
            "hits": targetClicks,
            "rt": rt.round(2),
            "numTargets": numTargets,
            "numdots": numCircles,
            "speed": mycircle.speed,
            "noise": mycircle.noise,
            "duration": trueDuration.round(2),
            "state": e.type,
            'seed': frame.message
        });

        
        if(frame.type === "test")
        {
            # update total
            total += numTargets

            # start a new trial
            setTimeout(function () {nextTrial();}, 1500)
        }
        else if(frame.type === "practice")
        {
            msg = "<br><br><br><br>You got " + targetClicks +
                      " of " + numTargets +
                      " dots correct.<br><br><br>"

            # deal with practice errors
            if(targetClicks < numTargets) :
            
                # we allow repeating practice trials 2 times
                if(practiceErr < 2) :
                
                    # rewind the trials chain by one
                    frameSequence.unshift(frame);

                    msg = "<br><br>Let's try again.<br><br>"+
                          "When the movement stops,<br>"+
                          "click the " + numTargets +
                          " dots that flashed.<br><br><br>";

                    practiceErr++;
                
            
            else practiceErr = 0;

            # give feedback
            setTimeout(function ()
            {
                showAlert(msg,
                          "Press continue",
                          function ()
                          {
                              showFrame("null");
                              nextTrial();
                          });
            }, 500);
        }
    }

    
    
def showMovingDots():
    
    motionTimer = 0
    motionIterations = 0
    
    # clear the canvas and feedback text
    if(paper) paper.clear();
    getID("textMiddle").innerHTML = "";
    
    # show the stimulus DIV and hide all others
    showFrame("canvasContainer","feedback");
    
    # set the random seed for each trial
    Math.seedrandom(frame.message);
    
    # initialize the dots
    setup();
    
    if(frame.type === "test")
    {
        # update and show the trial counter and score
        if(trialCount === 6 || demo === "true") trialCount = 0;
        trialCount++;
        getID("textLeft").innerHTML = trialCount + ' of 6';
        getID("textRight").innerHTML = 'Score ' + score;
    }
    
    # then set the motion scheduler
    function update()
    {
        # get a timestamp for the beginning of the motion
        if(!motionTimer) trueDuration = now();
    
        # increment the frame counter
        motionTimer++;
    
        # animate
        moveCircles();
    
        # exit the animation when we have reached the required duration
        if(motionTimer === motionIterations)
        {
            # compute real duration
            trueDuration = now() - trueDuration;
    
            # show the cursor again
            showCursor("canvasContainer");
    
            if (frame.type === "practice" ||
                frame.type === "test")
            {
                # start recording clicks
                for (j = 0; j < numCircles; j++)
                    circle[j].click(clickHandler);
    
                # set a timeout trap
                timeoutRef = setTimeout(function ()
                {
                    # remove the click handlers
                    for(k = 0; k < numCircles; k++)
                        circle[k].unclick(clickHandler);
    
                    results.push(
                    {
                        type: frame.type, # practice or test
                        hits: 0, # number of correct target clicks
                        rt: 0, # rt for this trial
                        numTargets: numTargets, # # of target dots
                        numdots: numCircles, # # of total dots
                        speed: mycircle.speed, # dot speed pixels/frame
                        noise: mycircle.noise, # +-deg added randomly to direction
                        duration: trueDuration.round(2), # total ms of animation
                        state: 'timeout', # click or timeout
                        seed: frame.message # random generator seed for this trial
                    });
    
                    # if we are debugging, log the results
                    if(debug === 'true') logResults();
    
                    if(frame.type === "test" && trialCount > 0)
                        trialCount--;
                    frameSequence.unshift(frame);
    
                    showAlert("<br><br>You took too long to respond!<br><br>" +
                              "Remember:<br>once the movement stops,<br>" +
                              "click the dots that flashed.<br><br><br>",
                              "Click here to retry",
                              function ()
                              {
                                  showFrame("null");
                                  nextTrial();
                              });
    
                }, clickTimeout);
    
                # initialize the clicks counter
                clicks = targetClicks = 0;
    
                # get a timestamp to calculate RT
                timestamp = now();
    
                if (frame.type === "practice")
                    getID("textMiddle").innerHTML = "Click the " +
                                                    numTargets +
                                                    " dots that flashed!";
    
                else if (frame.type === "test")
                    getID("textMiddle").innerHTML = "Click " + numTargets +
                                                    " dots"
            }
            else setTimeout(function ()
            {
                nextTrial();
            }, 1500);
        }
        else requestAnimationFrame(update);
    }
    
    chainTimeouts(
    function(){hideCursor("canvasContainer");},500,
    function(){requestAnimationFrame(ShowTargets);},100,
    function(){requestAnimationFrame(HideTargets);},100,
    function(){requestAnimationFrame(ShowTargets);},100,
    function(){requestAnimationFrame(HideTargets);},100,
    function(){requestAnimationFrame(ShowTargets);},100,
    function(){requestAnimationFrame(HideTargets);},100,
    function(){requestAnimationFrame(ShowTargets);},100,
    function(){requestAnimationFrame(HideTargets);},100,
    function(){requestAnimationFrame(ShowTargets);},100,
    function(){requestAnimationFrame(HideTargets);},1500,
    function ()
    {
        motionTimer = 0;
        motionIterations = Math.floor(duration/1000*60);
    
        requestAnimationFrame(update);
    });
        

def nextTrial():

    for (i = 0; i < numTargets; i++) targets[i] = 0;

    # read the frame sequence one frame at a time
    if(frame = frameSequence.shift())
    {
        # check if it's the startup frame
        if (frame.type === "begin")
            showAlert(frame.message,
            "Click here for instructions",
            function ()
            {
                nextTrial();
            });
        # else if it's a message frame, show it
        else if (frame.type === "message")
            showAlert(frame.message,
            "Click here to continue",
            function ()
            {
                showFrame("null");
                nextTrial();
            });
        # else show the animation
        else
        {
            numCircles=frame.n_circles;
            numTargets=frame.n_targets;
            mycircle.speed=frame.speed;
            duration=frame.duration;

            showMovingDots();
        }
    }
    # else the sequence is empty, we are done!
    else
    {
        outcomes.score = score;
        outcomes.correct = (score / total).round(3);
        outcomes.rtTotal = results.filter(function( obj )
                                         {return obj.type !== 'practice' &&
                                                 obj.state !== 'timeout';})
                                  .pluck("rt").sum().round(1);
        outcomes.frametime = frametime;

        if(debug === "true")
        console.log("Score is " + score + " out of " + total);

        # we either save locally or to the server
        if(showresults === "true" || autosave === 'true' || filename)
        {
            showAlert("<br><br>Your score is " + score + ".<br>" +
                      "<br>The test is over.<br>" +
                      "Thank you for participating!<br><br>",
                      "",
                      null);

            setTimeout(function()
            {
                if(filename === false) filename = "MOTresults.csv";
                tmbSubmitToFile(results,filename,autosave);
            },2000);
        }
        else
        {
            tmbSubmitToServer(results,score,outcomes,'/run.php');
        }
    }


def setFrameSequence():
    testMessage ={            
        "begin":["<h2>Multiple Object Tracking</h2>" ,
                    "<img src=MOT.gif><br><br>"],
        "instruction1":["<h2>Instructions:</h2>",
                        "<br><img src=happy-green-border.jpg><br>",
                        "<br>Keep track of the dots that flash,<br>",
                        "they have green smiles behind them.<br><br><br>"],
        "practice2":["<h2>Instructions:</h2>" ,
                        "Next time, when the movement stops,<br>",
                        "click the 2 dots that flashed.<br><br>",
                        "The other dots have<br>",
                        "red sad faces behind them.<br>",
                        "<img src=sad-red-border.jpg><br>",
                        "Try <b><i>not</i></b> to click on those.<br><br>"],
        "practice3":["<br><br><br>Good!<br><br>",
                        "Now we'll do the same thing with<br>",
                        "3 flashing dots.<br><br>"],
        "targets3":["<br><br>Great!<br><br>",
                    "Now we'll do 6 more with 3 dots.<br>",
                    "Motion is slow at first, then gets faster.<br>",
                    "This will be the first of 3 parts.<br><br>",
                    "When you lose track of dots, just guess.<br>",
                    "Your score will be the total number of<br>",
                    "green smiles that you click.<br><br>"],
        "targets4":["<br>Excellent!<br><br>",
                    "You have finished the first part of this test.<br>",  "" ,
                    "There are two parts left.<br><br>" ,
                    "The next part has 4 flashing dots.<br>",
                    "Motion is slow at first, then gets faster.<br><br>",
                    "When you lose track of dots, just guess.<br>",
                    "Every smile you click adds to your score!<br><br>"],
        "targets5":["<br>Outstanding!<br><br>",
                    "Now there is only one part left!<br><br>" ,
                    "The final part has 5 flashing dots!<br>",
                    "Motion is slow at first, then gets faster.<br><br>",
                    "When you lose track of dots, just guess.<br>",
                    "Every smile you click adds to your score!<br><br>"]
    }

    # set the random generator's seed
    s = seed;

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

    frame_ntargets = [0,0,2,0,2,0,3];
    frame_speed = [0,0,0.5,0,0.5,0,0.5];

    # instructions and practice phase
    for i in range(len(frameType)):            
        frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": frame_ntargets[i],
                    "n_circles": numCircles,
                    "speed": frame_speed[i],
                    "duration": 3000,
                    "message": frame_message[i]
                })
    

    # test 3 dots
    frame_type = ["message","test","test","test","test","test","test"];
    frame_message = [
        testMessage["targets3"],
        "test"+(s),
        "test"+(s+1),
        "test"+(s+2),
        "test"+(s+3),
        "test"+(s+4),
        "test"+(s+5),
        "test"+(s+6)]

    frame_speed = [0,1,2,3,4,5,6];

    for i in range(len(frameType)):            
        frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": 3,
                    "n_circles": numCircles,
                    "speed": frame_speed[i],
                    "duration": duration,
                    "message": frame_message[i]
                })

    # test 4 dots
    frame_message = [testMessage["targets4"],"test"+(s+10),"test"+(s+11),"test"+(s+12),
                        "test"+(s+13),"test"+(s+14),"test"+(s+15),"test"+(s+16)];

    for i in range(len(frameType)):            
        frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": 4,
                    "n_circles": numCircles,
                    "speed": frame_speed[i],
                    "duration": duration,
                    "message": frame_message[i]
                })

    # test 5 dots
    frame_message = [testMessage["targets5"],"test"+(s+20),"test"+(s+21),"test"+(s+22),
                        "test"+(s+23),"test"+(s+24),"test"+(s+25),"test"+(s+26)];

    for i in range(len(frameType)):            
        frameSequence.append(
                {
                    "type": frame_type[i],
                    "n_targets": 5,
                    "n_circles": numCircles,
                    "speed": frame_speed[i],
                    "duration": duration,
                    "message": frame_message[i]
                })

        


            # # disable spurious user interaction
            # disableSelect();
            # disableRightClick();
            # disableDrag();

            # setMobileViewportScale(560,600);

            # getFrameTime(10,function(interval){frametime = interval;});

            # images = ['MOT.gif','happy-green-border.jpg','sad-red-border.jpg'];

            # imagePreLoad(images,{callBack: setFrameSequence});
