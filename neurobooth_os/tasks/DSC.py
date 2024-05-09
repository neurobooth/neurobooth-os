# -*- coding: utf-8 -*-
"""
Created on Tue Nov 16 14:07:20 2021

@author: Adonay Nunes
"""

import os
import os.path as op
from typing import Union, Tuple, NamedTuple, List, Optional
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
from neurobooth_os.iout.stim_param_reader import get_cfg_path


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


class FrameDef(NamedTuple):
    type: str
    message: Optional[visual.ImageStim] = None
    symbol: int = 0

    @property
    def digit(self) -> int:
        if self.symbol == 0:
            return 0
        return 3 if self.symbol % 3 == 0 else self.symbol % 3

    @property
    def source(self) -> str:
        return f'key/{self.symbol}.gif'


class DSC(Task_Eyetracker):
    def __init__(self, path="", subj_id="test", task_name="DSC", duration=60, **kwargs):
        super().__init__(**kwargs)

        self.testVersion = "DSC_simplified_oneProbe_2019"
        self.task_name = task_name
        self.path_out = path
        self.subj_id = subj_id
        self.frameSequence: List[FrameDef] = []
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
        self.test_start_time = 0  # Sentinel value; test start time gets populated when running test frames.
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

    @classmethod
    def asset_path(cls, asset: Union[str, os.PathLike]) -> str:
        """
        Get the path to the specified asset.
        :param asset: The name of the asset/file.
        :return: The file system path to the asset in the config folder.
        """
        return op.join(get_cfg_path('assets'), 'DSC', asset)

    def load_image(self, asset: Union[str, os.PathLike], pos: Tuple[float, float] = (0, 0)) -> visual.ImageStim:
        """
        Locate the specified image  and create an image stimulus.
        :param asset: The name/path of the asset.
        :param pos: Override the default position of the stimulus on the screen.
        :return: An image stimulus containing of the requested image.
        """
        return visual.ImageStim(
            self.win,
            image=DSC.asset_path(asset),
            pos=pos,
            units="deg",
        )

    def run(self, prompt=True, last_task=False, subj_id="test", **kwarg):

        self.results = []  # array to store trials details and responses
        self.outcomes = {}  # object containing outcome variables
        self.test_start_time = 0

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

    def onreadyUI(self, frame: FrameDef, allow_next_frame: bool):

        # is the response correct?
        correct = self.tmbUI["response"][-1] == str(frame.digit)

        # store the results
        if frame.type == "practice" or (
            frame.type == "test" and self.tmbUI["status"] != "timeout"
        ):
            self.results.append(
                {
                    "type": frame.type,  # one of practice or test
                    "symbol": frame.symbol,  # symbol index
                    "digit": frame.digit,  # symbol digit
                    "response": self.tmbUI["response"][1],  # the key or element chosen
                    "correct": correct,  # boolean correct
                    "rt": self.tmbUI["rt"],  # response time
                    "timestamp": self.tmbUI["downTimestamp"],  # response timestamp
                    "state": self.tmbUI["status"],  # state of the response handler
                }
            )

        if frame.type == "practice":
            # on practice trials, stop sequence and advise participant if input timeout or not correct
            if self.tmbUI["status"] == "timeout" or not correct:
                # rewind frame sequence by one frame, so same frame is displayed again
                self.frameSequence.insert(0, frame)

                message = [
                    self.load_image(frame.source, pos=(0, 10)),
                    self.load_image('key/key.png'),
                    self.my_textbox2(
                        f"You should press {frame.digit} on the keyboard when you see this symbol",
                        (0, -8),
                    ),
                    self.load_image('frames/continue.png', pos=(0, -1)),
                ]

                present_msg(message, self.win)

        elif frame.type == "test":
            if allow_next_frame and self.tmbUI["status"] != "timeout":
                # Choose a symbol randomly, but avoid 1-back repetitions
                choices = [i for i in range(1, 6+1) if i != frame.symbol]
                symbol = random.choice(choices)

                # set up the next frame
                self.frameSequence.append(FrameDef(type='test', symbol=symbol))

    def nextTrial(self):
        # Keep presenting frames while there are still frames in the sequence
        while len(self.frameSequence):
            frame: FrameDef = self.frameSequence.pop(0)
            if frame.type in ["begin", "message"]:  # Check if it is an image frame
                present_msg([frame.message], self.win)
            else:  # Handle practice and test frames
                self.execute_frame(frame)

        # all test trials (excluding practice and timeouts)
        tmp1 = [
            r for r in self.results
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
                self.load_image('frames/continue.png'),
            ]

            present_msg(mes, self.win, key_resp="space")

        # SAVE RESULTS to file
        df_res = pd.DataFrame(self.results)
        df_out = pd.DataFrame.from_dict(self.outcomes, orient="index", columns=["vals"])

        res_fname = f"{self.subj_id}_{self.task_name}_results{self.rep}.csv"
        out_fname = f"{self.subj_id}_{self.task_name}_outcomes{self.rep}.csv"
        df_res.to_csv(op.join(self.path_out, res_fname))
        df_out.to_csv(op.join(self.path_out, out_fname))
        if len(self.task_files) >= 1:
            self.task_files = self.task_files.replace("}", "") + f", {res_fname}, {out_fname}" + "}"
        else:
            self.task_files += "{" + f"{res_fname}, {out_fname}" + "}"

        # Close win if just created for the task
        if self.win_temp:
            self.win.close()

    def elapsed_time(self) -> float:
        if self.test_start_time == 0:  # Set the test start on the first time this method is called.
            self.test_start_time = time.time()
        return time.time() - self.test_start_time

    def execute_frame(self, frame: FrameDef) -> None:
        stim = [
            self.load_image(frame.source, pos=(0, 10)),
            self.load_image('key/key.png'),
        ]

        # set response timeout:
        # - for practice trials -> a fixed interval
        if frame.type == "practice":
            self.tmbUI["timeout"] = 50
            allow_next_frame = True
        # - for test trials -> what's left of self.duration seconds since start, with a minimum of 150 ms
        else:
            time_remaining = self.tot_time - self.elapsed_time()
            self.tmbUI["timeout"] = max(time_remaining, 0.150)
            allow_next_frame = time_remaining > 0

        for s in stim:
            s.draw()
        self.win.flip()

        if frame.type == "practice":
            self.sendMessage(self.marker_practice_trial_start)
        else:
            self.sendMessage(self.marker_trial_start)
        self.sendMessage("TRIALID", to_marker=False)

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

            if frame.type == "practice":
                self.sendMessage(self.marker_practice_trial_end)
            else:
                self.sendMessage(self.marker_trial_end)

            self.onreadyUI(frame, allow_next_frame)

    def setFrameSequence(self):
        # Start with intro and instructions
        self.frameSequence.append(FrameDef(type='begin', message=self.load_image('frames/intro.png')))
        N_INSTR_FRAME = 8
        for i in range(N_INSTR_FRAME):
            self.frameSequence.append(FrameDef(type='message', message=self.load_image(f'frames/instruct_{i+1}.png')))

        # Three practice trials
        self.frameSequence.append(FrameDef(type='practice', symbol=1))
        self.frameSequence.append(FrameDef(type='practice', symbol=3))
        self.frameSequence.append(FrameDef(type='practice', symbol=5))

        # End of practice message
        self.frameSequence.append(FrameDef(type='message', message=self.load_image('frames/practice_end.png')))

        # Seed the task with one test trial
        self.frameSequence.append(FrameDef(type='test', symbol=4))


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
