#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tue Mar  9 14:55:50 2021

@author: adonay
"""
import random
import time
import os.path as op
import numpy as np
from psychopy import core, visual, event
from psychopy.visual.textbox2 import TextBox2
from psychopy import iohub
from psychopy.iohub import launchHubServer

def present_msg(elems, win, key_resp="return"):
    for e in elems:
        e.draw()
    win.flip()

    while not event.getKeys(keyList=key_resp):
        a = "next"
    print(a)



class DSC():

    def __init__(self, marker_outlet=None, win=None, **kwarg):
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
        self.fpath = op.dirname(op.abspath(__file__)).replace("\\", "/")
        self.tot_time = 10
        
        
        try:
            self.io = launchHubServer()
        except RuntimeError:
            io = iohub.client.ioHubConnection.ACTIVE_CONNECTION
            io.quit()
            self.io = launchHubServer()
        
        self.keyboard = self.io.devices.keyboard

        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
            # self.marker.push_sample([f"Streaming_0_{time.time()}"])
        else:
            self.with_lsl = False

        self.setup(win)
        self.nextTrial()
        self.io.quit()


    def send_marker(self, msg=None):
        # msg format str {word}_{value}
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])


    def my_textbox2(self, text, pos=(0,0), size=(None, None)):
        # xsize = min(len(text), 30)
        tbx = TextBox2(self.win, pos=pos, color='black', units='deg',lineSpacing=.7,
                       letterHeight=1.2, text=text, font="Arial", #size=(20, None),
                       borderColor=None, fillColor=None, editable=False, alignment='center')
        return tbx


    def setup(self, win):

        self.tmbUI["UIevents"] = ['keys'];
#        self.tmbUI["UIkeys"] = [keyToCode('1'),keyToCode('2'),keyToCode('3')]

        self.tmbUI['UIelements'] = ['resp1','resp2','resp3']
        self.tmbUI['highlight'] = "red"

        # create psychopy window
        if win is None:
            print("*No win provided")
            self.win = visual.Window((1800, 1070), monitor='testMonitor', allowGUI=True, color='white')
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False
            
        self.win.color = "white"
        self.win.flip()

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
                     "response": self.tmbUI["response"][1], # the key or element chosen
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
                visual.ImageStim(self.win, image=self.fpath+'/DSC/images/key.png', pos=(0, 0), units='deg'),
                self.my_textbox2(f"You should press <b>{frame['digit']}</b> on the <b>keyboard</b> " +\
                                            "when you see this symbol", (0, -7)),
                self.my_textbox2('Press [enter] to continue', (0, -10)),
                ]

                present_msg(message, self.win)


        elif frame["type"] == "test":

            if self.tmbUI["status"] != "timeout":
                # print(f"making frame, status {self.tmbUI['status']}")
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
                        "source": self.fpath + f'/DSC/images/{symbol}.gif'
                        })



    def nextTrial(self):

        # take next frame sequence
        while len(self.frameSequence):
             # read the frame sequence one frame at a time
            frame = self.frameSequence.pop(0)

            # check if it's the startup frame
            if frame["type"] in ["begin", "message"]:

                present_msg(frame["message"], self.win)

            # deal with practice and test frames
            else:

                stim = [
                    visual.ImageStim(self.win, image=frame["source"], pos=(0, 6), units='deg'),
                    visual.ImageStim(self.win, image=self.fpath + '/DSC/images/key.png', pos=(0, 0), units='deg'),
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
                        self.tmbUI["timeout"] = self.tot_time - (time.time() - self.testStart);

                    if self.tmbUI["timeout"] < .150:
                        self.tmbUI["timeout"] = .150
                        # print("Timeout small, turned to .150")

                for s in stim:
                    s.draw()
                self.win.flip()

                self.send_marker("Trial-start_0")
                trialClock = core.Clock()
                countDown = core.CountdownTimer().add(self.tmbUI["timeout"])

                countDown = core.CountdownTimer()
                countDown.add(self.tmbUI["timeout"])

                kpos = [-2.2, 0, 2.2]
                trialClock = core.Clock()
                timed_out = True
                while countDown.getTime() > 0:
                    key = event.getKeys(keyList=['1', '2', '3'], timeStamped=True)
                    if key:                        
                        kvl = key[0][0]
                        self.send_marker("Trial-res_0")
                        self.tmbUI["rt"] = trialClock.getTime()
                        self.tmbUI["response"] = ["key", key[0][0]]
                        self.tmbUI["downTimestamp"] = key[0][1]
                        self.tmbUI["status"] = "Ontime"
                        timed_out = False
                        self.send_marker("Trial-res_1")
                        rec_xpos = kpos[int(key[0][0])-1]
                        stim.append(
                            visual.Rect(self.win, units='deg', lineColor='red',
                                        pos=(rec_xpos,-2.6), size=(2.5,2.5),
                                        lineWidth=4))

                        _ = self.keyboard.getReleases()
                        for ss in stim:
                            ss.draw()
                        self.win.flip()
                        response_events = self.keyboard.waitForReleases()
                        break

                if timed_out:
                    print("timed out")
                    self.tmbUI["status"] = "timeout"
                    self.tmbUI["response"] = ["key", ""]
                self.send_marker("Trial-end_1")
                self.onreadyUI(frame)

        # elif the sequence is empty, we are done!
        print("Sequence frames done")

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
            mes = [self.my_textbox2(f"Your score is {score}. \nThe test is " + \
                      "over. \nThank you for participating!",(0, 2)),
            self.my_textbox2('Press <b>[enter]</b> to continue', pos=(0, -7))
            ]

            present_msg(mes, self.win, key_resp="return")
            
        # Close win if just created for the task
        if self.win_temp:
            self.win.close()
        else:
            self.win.flip()

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
                self.my_textbox2("Digit-Symbol Coding Test", (0, 6)),

                self.my_textbox2('Press <b>[enter]</b> for instructions', (0, -6)),

                visual.ImageStim(self.win, image=self.fpath + '/DSC/images/key.png', pos=(0, 0), units='deg')
                ],

            "practice": [
                [
                    self.my_textbox2("Instructions",(0, 6)),

                    self.my_textbox2("Each <b>symbol</b> has a <b>number</b>",(0, -5)),

                    self.my_textbox2('Press [enter] to continue',(0, -7)),

                    visual.ImageStim(self.win, image=self.fpath+'/DSC/images/key.png', pos=(0, 0), units='deg')
                ],

                [
                    visual.ImageStim(self.win, image=self.fpath+'/DSC/images/1.gif', pos=(0, 6), units='deg'),

                    visual.ImageStim(self.win, image=self.fpath+'/DSC/images/key.png', pos=(0, 0), units='deg'),

                    self.my_textbox2("When a symbol appears at the top, " +
                           "press its number on the <b>keyboard</b> \n" +
                          "(here it is  <b>1</b>).", (0, -6)),

                    self.my_textbox2( 'Press <b>[enter]</b> to continue',(0, -10)),
                    ],
                [
                    visual.ImageStim(self.win, image=self.fpath+'/DSC/images/2.gif', pos=(0, 6), units='deg'),

                    visual.ImageStim(self.win, image=self.fpath+'/DSC/images/keySmall.png', pos=(0, 0), units='deg'),

                    self.my_textbox2("Let's practice a few symbols.", (0, -6))
                    ]
                ],
            "test":[
                self.my_textbox2("Excellent! \nYou have completed the practice.\n " +\
                                    "Now let's do more.", (0, 6)),

                 self.my_textbox2("Your score will be how many correct responses you" +
                             " make in a minute and a half,so try to be \
                                 <b>ACCURATE</b> and <b>QUICK</b>!", (0, -4)),
                 self.my_textbox2( 'Press <b>[enter]</b> to continue',(0, -10))
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
                    "source":self.fpath + f'/DSC/images/{frameSymbol[i]}.gif'
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

