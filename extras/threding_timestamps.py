# -*- coding: utf-8 -*-
"""
Created on Sat Apr 30 18:53:10 2022

@author: STM
"""

import time
import threading
import numpy as np

import pylink
from psychopy import core, event
from pylsl import local_clock
import matplotlib.pyplot as plt



class EyeTracker():        
        
    def start(self):

        self.recording = True
        self.stream_thread = threading.Thread(target=self.record)
        self.stream_thread.start()

    def record(self):
      
        self.timestamps_local = []
        while self.recording:

            t1 = local_clock()
            t2 = t1
            self.timestamps_local.append(t1)
            
            while t2-t1 < .001/4:
                t2 = local_clock() 

    def stop(self):
        self.recording = False


def countdown(period):
    t1 = local_clock()
    t2 = t1
    
    while t2-t1 < period:
        t2 =local_clock()


def get_keys(keyList=()):
    # Wait for keys checking every 5 ms
    while True:
        press =  event.getKeys()
        if press:
            if keyList and press in keyList:
                    return press
            else:
                return press   
        countdown(.005)
        


def make_win(full_screen=True, monitor_width=55, 
             subj_screendist_cm=60 
             ):
    mon = monitors.getAllMonitors()[0]
    customMon = monitors.Monitor('demoMon', width=monitor_width, distance=subj_screendist_cm)

    mon_size = monitors.Monitor(mon).getSizePix()
    customMon.setSizePix(mon_size)
    customMon.saveMon()
    win = visual.Window(
        mon_size,
        fullscr=full_screen,
        monitor=customMon,
        units='pix',
        color=(0, 0, 0)
        )
    print("Monitor Set Refresh Rate:{:.2f} Hz".format(1/win.monitorFramePeriod))
    print("Monitor Actual Refresh Rate:{:.2f} Hz".format(win.getActualFrameRate(nIdentical=30, nMaxFrames=300,
                                                                                nWarmUpFrames=10, threshold=1)))
    return win

if __name__ == "__main__":
    
    win = make_win(False)
    et = EyeTracker()
    et.start()
    countdown(10)
    et.stop()
    td = np.diff(et.timestamps_local)
    print(f"pylsl local clock: {np.mean(1/td)}, {len(td)}")
    plt.figure()
    plt.plot(td, label='pylsl local')
    
  
    et = EyeTracker()
    et.start()
    core.wait(10, 1)
    et.stop()
    td = np.diff(et.timestamps_local)
    print(f"core wait 1sec cpuhog: {np.mean(1/td)}, {len(td)}")
    plt.plot(td, label='core.wait')
    
    
    et = EyeTracker()
    et.start()
    pylink.msecDelay(10000)
    et.stop()
    td = np.diff(et.timestamps_local)
    print(f"pylink msecDelay: {np.mean(1/td)}, {len(td)}")
    plt.plot(td, label="pylink.msecDelay")
    
    print('click on psychopy window and press any key after 10 secs')
    time.sleep(.5) 
   
    et = EyeTracker()
    et.start()      
    event.waitKeys()
    et.stop()
    td = np.diff(et.timestamps_local)
    print(f"event.waitKeys: {np.mean(1/td)}, {len(td)}")
    plt.plot(td, label="event.waitKeys")
    
    print('click on psychopy window and press any key after 10 secs')
    time.sleep(.5)
   
    et = EyeTracker()
    et.start()      
    get_keys()
    et.stop()
    td = np.diff(et.timestamps_local)
    print(f"get_keys: {np.mean(1/td)}, {len(td)}")
    plt.plot(td, label="get_keys") 
    
    win.close()
    plt.legend()
    
    
    
    
    
    
    
    