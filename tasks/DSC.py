#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar  9 14:55:50 2021

@author: adonay
"""
import random
import time
import numpy as np
from psychopy import core, visual, event


def present_msg(elems, win, key_resp="return"):
    for e in elems:
        e.draw()
    win.flip()

    while not event.getKeys(keyList=key_resp):
        a = "next"
    print(a)  


class DSC():
    
    def __init__(self, marker_outlet=None):
        self.testVersion = 'DSC_simplified_oneProbe_2019' 
        self.chosenInput = 'keys'    # input type (taps or keys)
        self.frameSequence = []
        self.tmbUI = dict.fromkeys(["response", "symbol", "digit", "message", 
                                    "status", "rt", "downTimestamp", ])
        self.showresults = True               #  # URL parameter: if they want to show results in a popup window
        self.results = []            #    # array to store trials details and responses        
        self.outcomes = {}             # # object containing outcome variables     
        self.testStart = 0       #        # start timestamp of the test
        self.demo = False                   #      # URL parameter: run in demo mode
        self.filename = "fname.csv"           #        # filename for data     
        
        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
            # outlet_marker.push_sample([f"Streaming_0_{time.time()}"])
        self.setup()
        self.nextTrial()             

    def send_marker(self, msg=None):
        # msg format str {word}_{value}
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])
        
        
    def setup(self):
 
        self.tmbUI["UIevents"] = ['keys'];
#        self.tmbUI["UIkeys"] = [keyToCode('1'),keyToCode('2'),keyToCode('3')]

        self.tmbUI['UIelements'] = ['resp1','resp2','resp3']
        self.tmbUI['highlight'] = "red"

        # create psychopy window
        self.win = visual.Window((800, 800), monitor='testMonitor', allowGUI=True, color='white')
        
        # create the trials chain
        self.setFrameSequence()


    def onreadyUI(self, frame):
    
        #is the response correct?
        correct = self.tmbUI["response"][-1] == str(frame["digit"])
    
        # store the results
        if frame["type"] == "practice" or (frame["type"] == "test" and
                                           self.tmbUI["status"] != "timeout"):
    
             self.results.append({
                     "type": frame["type"], # one of practice or test
                     "symbol": frame["symbol"], # symbol index
                     "digit": frame["digit"], # symbol digit
                     "response": self.tmbUI["response"][0], # the key or element chosen
                     'correct': correct, # boolean correct
                     "rt": self.tmbUI["rt"], # response time
                     "timestamp": self.tmbUI["downTimestamp"], # response timestamp
                     "state": self.tmbUI["status"] # state of the response handler
                     })
    
        if frame["type"] == "practice":
    
            # on practice trials, if the input event returns a timeout
            # or the response is not correct,
            # stop the sequence and advise the participant
            if self.tmbUI["status"] == "timeout" or not correct:
                print(f"corr: {correct}, status: {self.tmbUI['status']}")
                # rewind the frame sequence by one frame,
                # so that the same frame is displayed again
                self.frameSequence.insert(0, frame)
                        
                message = [
                visual.ImageStim(self.win, image=frame["source"], pos=(0, 6), units='deg'),
                visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\key.png', pos=(0, 0), units='deg'),
                visual.TextStim(self.win, pos=(0, -7), bold=True, height=1.2, depth=2,                                    
                                        text=f"You should press <b>{frame['digit']}</b> on the <b>keyboard</b> " +\
                                            "when you see this symbol",
                                        color='black', units='deg'),
                 visual.TextStim(self.win, pos=(0, -10), color='black', units='deg',
                                                text='Press [enter] to continue'),     
                ]
                
                present_msg(message, self.win) 

                self.nextTrial()
    
            else:
                self.nextTrial()
    
        elif frame["type"] == "test":
    
            if self.tmbUI["status"] != "timeout":
    
                # choose a symbol randomly, but avoid 1-back repetitions
                while True:    
                    symbol = random.randint(1, 6)
                    if symbol != frame["symbol"]:
                        break
    
                digit = 3 if symbol % 3 == 0 else symbol % 3
    
                # set up the next frame
                self.frameSequence.append({                    
                        "type": "test",
                        "message": "",
                        "symbol": symbol,
                        "digit": digit,
                        "source": f"C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\{symbol}.gif"
                        })
    
            self.nextTrial()

         
    def nextTrial(self):
    
        # take next frame sequence
        if len(self.frameSequence):
             # read the frame sequence one frame at a time
            frame = self.frameSequence.pop(0)
    
            # check if it's the startup frame
            if frame["type"] in ["begin", "message"]:
                
                present_msg(frame["message"], self.win)                
    
                self.nextTrial();
    
            # deal with practice and test frames
            else:
    
                stim = [
                    visual.ImageStim(self.win, image=frame["source"], pos=(0, 6), units='deg'),
                    visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\key.png', pos=(0, 0), units='deg'),
                    ]
    
                # set response timeout:
                # - for practice trials -> a fixed interval
                # - for test trials -> what's left of 90 seconds since start,
                #                      with a minimum of 150 ms
                if frame["type"] == "practice":
                    self.tmbUI["timeout"] = 50
                else:
    
                    if not self.testStart:
                        self.testStart = time.time()
    
                    if self.demo == 'true':
                        self.tmbUI["timeout"] = 100 - (time.time() - self.testStart);
    
                    else:
                        self.tmbUI["timeout"] = 90 - (time.time() - self.testStart);
    
                    if self.tmbUI["timeout"] < .150:
                        self.tmbUI["timeout"] = .150
    
                for s in stim:
                    s.draw()
                self.win.flip()
                self.send_marker("Trial-start_0")
                trialClock = core.Clock()
                countDown = core.CountdownTimer().add(self.tmbUI["timeout"])
        
                countDown = core.CountdownTimer()
                countDown.add(self.tmbUI["timeout"])
    
                trialClock = core.Clock()
                timed_out = True
                while countDown.getTime() > 0:
                    key = event.getKeys(keyList=['1', '2', '3'], timeStamped=True)
                    if key:
                        # TODO highlight red
                        print(key)
                        self.send_marker("Trial-res_0")
                        self.tmbUI["rt"] = trialClock.getTime()
                        self.tmbUI["response"] = ["key", key[0][0]]
                        self.tmbUI["downTimestamp"] = key[0][1]
                        self.tmbUI["status"] = "Ontime"
                        timed_out = False
                        self.send_marker("Trial-res_1")
                        break
                    
                if timed_out:
                    self.tmbUI["status"] != "timeout"
                    self.tmbUI["response"] = ["key", ""]
                self.send_marker("Trial-end_1")
                self.onreadyUI(frame)
    
        # elif the sequence is empty, we are done!
        else:
    
            # all test trials (excluding practice and timeouts)
            tmp1 = [r for r in self.results
                    if r["type"] != 'practice' and  r["state"] != 'timeout']
    
            # all correct rts
            tmp2 = [r['rt'] for r in self.results  if r["correct"] ]
    
            # compute score and outcome variables
            score = self.outcomes["score"] = len(tmp2)
            self.outcomes["num_correct"] = len(tmp2)
            self.outcomes["num_responses"] = len(tmp1)
            self.outcomes["meanRTc"] = np.mean(tmp2)
            self.outcomes["medianRTc"] = np.median(tmp2)
            self.outcomes["sdRTc"] = round(np.std(tmp2), 2)
            self.outcomes["responseDevice"] = 'keyboard'
            self.outcomes["testVersion"] = self.testVersion
    
    
            if self.showresults: 
                mes = [visual.TextStim(self.win, pos=(0, 2), bold=True, height=1.2, depth=2,                                    
                                        text=f"Your score is {score}. \n " +
                          "The test is over. \nThank you for participating!",
                                        color='black', units='deg'),                
                visual.TextStim(self.win, pos=(0, -7), color='black', units='deg',
                                                text='Press [enter] to continue')                
                ]
                
                present_msg(mes, self.win, key_resp="return")
                
                
            # TODO:     SAVE RESULTS AS YOU LIKE THE MOST
            #                
            #                
            #                
            #                if(filename == false): filename = "DSCresults.csv";
            #                tmbSubmitToFile(results,filename,autosave);
            #    
            #            else:
            #    
            #                tmbSubmitToServer(results,score,outcomes);
    
    

    def setFrameSequence(self):

        # messages
        testMessage ={
            "begin": [
                visual.TextStim(self.win, pos=(0, 6), bold=True, height=1.2,
                                depth=2, text="Digit-Symbol Coding Test",
                                color='black', units='deg'),

                visual.TextStim(self.win, pos=(0, -6), color='black', units='deg',
                                        text='Press [enter] for instructions'),

                visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\key.png', pos=(0, 0), units='deg')
                ],

            "practice": [
                [
                    visual.TextStim(self.win, pos=(0, 6), bold=True, height=1.2,
                                    depth=2, text="Instructions",
                                    color='black', units='deg'),

                    visual.TextStim(self.win, pos=(0, -5), bold=True, height=1.2,
                                    depth=2, text="Each <b>symbol</b> has a <b>number</b>",
                                    color='black', units='deg'),

                    visual.TextStim(self.win, pos=(0, -7), color='black', units='deg',
                                            text='Press [enter] to continue'),

                    visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\key.png', pos=(0, 0), units='deg')
                ],

                [
                    visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\1.gif', pos=(0, 6), units='deg'),

                    visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\key.png', pos=(0, 0), units='deg'),

                    visual.TextStim(self.win, pos=(0, -6), color='black', units='deg',
                                            text="When a symbol appears at the top, " +
                           "press its number on the <b>keyboard</b> \n" +
                          "(here it is 1)."),

                    visual.TextStim(self.win, pos=(0, -10), color='black', units='deg',
                                            text='Press [enter] to continue'),
                    ],
                [
                    visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\2.gif', pos=(0, 6), units='deg'),

                    visual.ImageStim(self.win, image='C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\keySmall.png', pos=(0, 0), units='deg'),

                    visual.TextStim(self.win, pos=(0, -6), color='black', units='deg',
                                            text="Let's practice a few symbols.")
                    ]
                ],
            "test":[
                visual.TextStim(self.win, pos=(0, 6), bold=True, height=1.2,
                                    color='black', units='deg', text="Excellent! \n" +\
                                    "You have completed the practice.\n " +\
                                    "Now let's do more." ),

                 visual.TextStim(self.win, pos=(0, -6), bold=True, height=1.2,
                                    color='black', units='deg',
                                    text="Your score will be how many correct \
                                        responses you make in a minute and a half,\
                                            so try to be <b>ACCURATE</b> and <b>QUICK</b>!")
                ]
                                 }
    
        # type of frame to display
        frameType = ["begin",
                     "message",
                     "message",
                     "practice",
                     "practice",
                     "practice",
                     "message",
                     "test"]

        # message to display
        frameMessage = [testMessage["begin"],
                        testMessage["practice"][0],
                        testMessage["practice"][1],
                        "",
                        "",
                        "",
                        testMessage["test"],""]

        # symbol to display
        frameSymbol = [0,0,0,1,3,5,0,4];

        # corresponding digit
        frameDigit = [0,0,0,1,3,2,0,1];
            
        # push all components into the frames chain
        for i in range(len(frameType)):
            self.frameSequence.append(
                    {
                    "type": frameType[i],
                    "message": frameMessage[i],
                    "symbol": frameSymbol[i],
                    "digit": frameDigit[i],
                    "source": f"C:\\neurobooth\\neurobooth-eel\\tasks\\DSC\\images\\{frameSymbol[i]}.gif"
                    })
        










#         <img id="probe" class="img-responsive" src="images/1.gif">
#     </div>
#     <br><br>
#     <div id="keyRow1">
#         <img src="images/1.gif">
#         <img src="images/2.gif">
#         <img src="images/3.gif">
#     </div>
#     <div id="keyRow2">
#         <img src="images/4.gif">
#         <img src="images/5.gif">
#         <img src="images/6.gif">
#     </div>
#     <div id="response">
#         <img class="img-responsive" id="resp1" src="images/resp1.png">
#         <img class="img-responsive" id="resp2" src="images/resp2.png">
#         <img class="img-responsive" id="resp3" src="images/resp3.png">
#     </div>
# </div>

