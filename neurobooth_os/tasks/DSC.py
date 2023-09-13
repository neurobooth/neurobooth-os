# -*- coding: utf-8 -*-
"""
Created on Tue Nov 16 14:07:20 2021

@author: Adonay Nunes
"""

import os.path as op
import random
import time
from datetime import datetime
import numpy as np
import pandas as pd

from psychopy import core, visual, event, iohub
from psychopy.iohub import launchHubServer
from psychopy.visual.textbox2 import TextBox2

import neurobooth_os
from neurobooth_os.tasks import utils
from neurobooth_os.tasks import Task_Eyetracker


def my_textbox2(win, text, pos=(0, 0), size=(None, None)):

    tbx = TextBox2(
        win,
        pos=pos,
        color="black",
        units="pix",
        lineSpacing=0.9,
        letterHeight=20,
        text=text,
        font="Arial",  # size=(20, None),
        borderColor=None,
        fillColor=None,
        editable=False,
        alignment="center",
    )
    return tbx


def present_msg(elems, win, key_resp="space"):
    for e in elems:
        e.draw()
    win.flip()
    utils.get_keys(keyList=[key_resp])


class DSC(Task_Eyetracker):
    def __init__(self, path="", subj_id="test", task_name="DSC", duration=60, **kwargs):
        super().__init__(**kwargs)

        self.testVersion = "DSC_simplified_oneProbe_2019"
        self.task_name = task_name
        self.path_out = path
        self.subj_id = subj_id
        self.frameSequence = []
        self.tmbUI = dict.fromkeys(
            [
                "response",
                "symbol",
                "digit",
                "message",
                "status",
                "rt",
                "downTimestamp",
            ]
        )

        self.results = []  # array to store trials details and responses
        self.outcomes = {}  # object containing outcome variables
        self.testStart = 0  # start timestamp of the test
        self.rootdir = op.join(neurobooth_os.__path__[0], "tasks", "DSC")
        self.tot_time = duration
        self.showresults = False
        self.rep = ""  # repeated task num to add to filename
        self.task_files = ""

        try:
            self.io = launchHubServer()
        except RuntimeError:
            io = iohub.client.ioHubConnection.ACTIVE_CONNECTION
            io.quit()
            self.io = launchHubServer()

        self.keyboard = self.io.devices.keyboard

        self.setup(self.win)

    def run(self, prompt=True, last_task=False, subj_id="test", **kwargs):

        self.results = []  # array to store trials details and responses
        self.outcomes = {}  # object containing outcome variables
        self.testStart = 0

        # Check if run previously, create framesequence again
        if len(self.frameSequence) == 0:
            self.setFrameSequence()

        self.subj_id = subj_id
        self.present_instructions(prompt)

        self.win.color = "white"
        self.win.flip()

        self.sendMessage(self.marker_task_start, to_marker=True, add_event=True)
        self.nextTrial()
        self.sendMessage(self.marker_task_end, to_marker=True, add_event=True)

        if prompt:
            func_kwargs_func = {"prompt": prompt}
            self.rep += "_I"
            self.show_text(
                screen=self.press_task_screen,
                msg="Task-continue-repeat",
                func=self.run,
                func_kwargs=func_kwargs_func,
                waitKeys=False,
            )

        self.io.quit()
        self.present_complete(last_task)
        return self.events

    def wait_release(self, keys=None):
        while True:
            rels = self.keyboard.getReleases(keys=keys)
            if len(rels):
                return rels
            utils.countdown(0.001)

    def my_textbox2(self, text, pos=(0, 0), size=(None, None)):
        tbx = TextBox2(
            self.win,
            pos=pos,
            color="black",
            units="deg",
            lineSpacing=0.9,
            letterHeight=1,
            text=text,
            font="Arial",  # size=(20, None),
            borderColor=None,
            fillColor=None,
            editable=False,
            alignment="center",
        )
        return tbx

    def setup(self, win):

        self.tmbUI["UIevents"] = ["keys"]
        self.tmbUI["UIelements"] = ["resp1", "resp2", "resp3"]
        self.tmbUI["highlight"] = "red"

        # create the trials chain
        self.setFrameSequence()

    def onreadyUI(self, frame):

        # is the response correct?
        correct = self.tmbUI["response"][-1] == str(frame["digit"])

        # store the results
        if frame["type"] == "practice" or (
            frame["type"] == "test" and self.tmbUI["status"] != "timeout"
        ):
            self.results.append(
                {
                    "type": frame["type"],  # one of practice or test
                    "symbol": frame["symbol"],  # symbol index
                    "digit": frame["digit"],  # symbol digit
                    "response": self.tmbUI["response"][1],  # the key or element chosen
                    "correct": correct,  # boolean correct
                    "rt": self.tmbUI["rt"],  # response time
                    "timestamp": self.tmbUI["downTimestamp"],  # response timestamp
                    "state": self.tmbUI["status"],  # state of the response handler
                }
            )

        if frame["type"] == "practice":

            # on practice trials, stop sequence and advise participant if input timeout or not correct
            if self.tmbUI["status"] == "timeout" or not correct:
                # rewind frame sequence by one frame, so same frame is displayed again
                self.frameSequence.insert(0, frame)

                message = [
                    visual.ImageStim(
                        self.win, image=frame["source"], pos=(0, 10), units="deg"
                    ),
                    visual.ImageStim(
                        self.win,
                        image=op.join(self.rootdir, "images/key.png"),
                        pos=(0, 0),
                        units="deg",
                    ),
                    self.my_textbox2(
                        f"You should press {frame['digit']} on the keyboard when you see this symbol",
                        (0, -8),
                    ),
                    visual.ImageStim(
                        self.win,
                        image=op.join(self.rootdir, "continue.png"),
                        pos=(0, -1),
                        units="deg",
                    ),
                ]

                present_msg(message, self.win)

        elif frame["type"] == "test":

            if self.tmbUI["status"] != "timeout":
                # choose a symbol randomly, but avoid 1-back repetitions
                while True:
                    symbol = random.randint(1, 6)
                    if symbol != frame["symbol"]:
                        break

                digit = 3 if symbol % 3 == 0 else symbol % 3

                # set up the next frame
                self.frameSequence.append(
                    {
                        "type": "test",
                        "message": "",
                        "symbol": symbol,
                        "digit": digit,
                        "source": op.join(self.rootdir, f"images/{symbol}.gif"),
                    }
                )

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
                    visual.ImageStim(
                        self.win, image=frame["source"], pos=(0, 10), units="deg"
                    ),
                    visual.ImageStim(
                        self.win,
                        image=op.join(self.rootdir, "images/key.png"),
                        pos=(0, 0),
                        units="deg",
                    ),
                ]

                # set response timeout:
                # - for practice trials -> a fixed interval
                # - for test trials -> what's left of self.duration seconds since start, with a minimum of 150 ms
                if frame["type"] == "practice":
                    self.tmbUI["timeout"] = 50
                else:
                    if self.testStart == 0:
                        self.testStart = time.time()

                    self.tmbUI["timeout"] = self.tot_time - (
                        time.time() - self.testStart
                    )
                    if self.tmbUI["timeout"] < 0.150:
                        self.tmbUI["timeout"] = 0.150

                for s in stim:
                    s.draw()
                self.win.flip()

                if frame["type"] == "practice":
                    self.sendMessage(self.marker_practice_trial_start)
                else:
                    self.sendMessage(self.marker_trial_start)
                self.sendMessage("TRIALID", to_marker=False)

                trialClock = core.Clock()
                countDown = core.CountdownTimer().add(self.tmbUI["timeout"])

                countDown = core.CountdownTimer()
                countDown.add(self.tmbUI["timeout"])

                kpos = [-4.2, 0, 4.2]
                trialClock = core.Clock()
                timed_out = True
                while countDown.getTime() > 0:
                    key = event.getKeys(keyList=["1", "2", "3", "q"], timeStamped=True)
                    if key:
                        kvl = key[0][0]
                        if kvl == "q":
                            print("DSC Task aborted")
                            self.frameSequence = []
                            break

                        self.sendMessage(self.marker_response_start)
                        self.tmbUI["rt"] = trialClock.getTime()
                        self.tmbUI["response"] = ["key", key[0][0]]
                        self.tmbUI["downTimestamp"] = key[0][1]
                        self.tmbUI["status"] = "Ontime"
                        timed_out = False

                        rec_xpos = [kpos[int(key[0][0]) - 1], -4.5]
                        self.send_target_loc(rec_xpos, "target_box")

                        stim.append(
                            visual.Rect(
                                self.win,
                                units="deg",
                                lineColor="red",
                                pos=rec_xpos,
                                size=(3.5, 3.5),
                                lineWidth=4,
                            )
                        )

                        _ = self.keyboard.getReleases()
                        for ss in stim:
                            ss.draw()
                        self.win.flip()
                        response_events = self.wait_release()
                        self.sendMessage(self.marker_response_end)
                        break
                    utils.countdown(0.001)

                if timed_out:
                    print("timed out")
                    self.tmbUI["status"] = "timeout"
                    self.tmbUI["response"] = ["key", ""]

                if frame["type"] == "practice":
                    self.sendMessage(self.marker_practice_trial_end)
                else:
                    self.sendMessage(self.marker_trial_end)
                self.onreadyUI(frame)

        # all test trials (excluding practice and timeouts)
        tmp1 = [
            r
            for r in self.results
            if r["type"] != "practice" and r["state"] != "timeout"
        ]

        # all correct rts
        tmp2 = [r["rt"] for r in tmp1 if r["correct"]]

        # compute score and outcome variables
        score = self.outcomes["score"] = len(tmp2)
        self.outcomes["num_correct"] = len(tmp2)
        self.outcomes["num_responses"] = len(tmp1)
        self.outcomes["meanRTc"] = np.mean(tmp2)
        self.outcomes["medianRTc"] = np.median(tmp2)
        self.outcomes["sdRTc"] = round(np.std(tmp2), 2)
        self.outcomes["responseDevice"] = "keyboard"
        self.outcomes["testVersion"] = self.testVersion

        if self.showresults:
            mes = [
                self.my_textbox2(
                    f"Your score is {score}. \nThe test is "
                    + "over. \nThank you for participating!",
                    (0, 2),
                ),
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "continue.png"),
                    pos=(0, 0),
                    units="deg",
                ),
            ]

            present_msg(mes, self.win, key_resp="space")

        # SAVE RESULTS to file
        df_res = pd.DataFrame(self.results)
        df_out = pd.DataFrame.from_dict(self.outcomes, orient="index", columns=["vals"])

        res_fname = f"{self.subj_id}_{self.task_name}_results{self.rep}.csv"
        out_fname = f"{self.subj_id}_{self.task_name}_outcomes{self.rep}.csv"
        df_res.to_csv(self.path_out + res_fname)
        df_out.to_csv(self.path_out + out_fname)
        if len(self.task_files) >= 1:
            self.task_files = self.task_files.replace("}", "") + f", {res_fname}, {out_fname}" + "}"
        else:
            self.task_files += "{" + f"{res_fname}, {out_fname}" + "}"

        # Close win if just created for the task
        if self.win_temp:
            self.win.close()
        else:
            stim = visual.ImageStim(
                self.win,
                image=op.join(self.rootdir, "task_complete.png"),
                pos=(0, 0),
                units="deg",
            )
            stim.draw()
            self.win.flip()

    def setFrameSequence(self):
        testMessage = {
            "begin": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "intro.png"),
                    pos=(0, 0),
                    units="deg",
                )
            ],
            "practice": [
                [
                    visual.ImageStim(
                        self.win,
                        image=op.join(self.rootdir, "intruct_1.png"),
                        pos=(0, 0),
                        units="deg",
                    )
                ],
                [
                    visual.ImageStim(
                        self.win,
                        image=op.join(self.rootdir, "intruct_2.png"),
                        pos=(0, 0),
                        units="deg",
                    ),
                ],
                [
                    visual.ImageStim(
                        self.win,
                        image=op.join(self.rootdir, "intruct_3.png"),
                        pos=(0, 0),
                        units="deg",
                    ),
                ],
            ],
            "test": [
                visual.ImageStim(
                    self.win,
                    image=op.join(self.rootdir, "practice_end.png"),
                    pos=(0, 0),
                    units="deg",
                ),
            ],
        }

        # type of frame to display
        frameType = [
            "begin",
            "message",
            "message",
            "message",
            "practice",
            "practice",
            "practice",
            "message",
            "test",
        ]

        # message to display
        frameMessage = [
            testMessage["begin"],
            testMessage["practice"][0],
            testMessage["practice"][1],
            testMessage["practice"][2],
            "",
            "",
            "",
            testMessage["test"],
            "",
        ]

        # symbol to display
        frameSymbol = [0, 0, 0, 0, 1, 3, 5, 0, 4]

        # corresponding digit
        frameDigit = [0, 0, 0, 0, 1, 3, 2, 0, 1]

        # push all components into the frames chain
        for i in range(len(frameType)):
            self.frameSequence.append(
                {
                    "type": frameType[i],
                    "message": frameMessage[i],
                    "symbol": frameSymbol[i],
                    "digit": frameDigit[i],
                    "source": op.join(self.rootdir, f"images/{frameSymbol[i]}.gif"),
                }
            )


if __name__ == "__main__":
    from psychopy import sound, core, event, monitors, visual, monitors

    monitor_width = 55
    monitor_distance = 60
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor(
        "demoMon", width=monitor_width, distance=monitor_distance
    )
    win = visual.Window(
        [1920, 1080], fullscr=False, monitor=customMon, units="pix", color="white"
    )

    self = DSC(win=win)
    self.run()
    win.close()
