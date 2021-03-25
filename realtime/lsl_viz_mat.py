# -*- coding: utf-8 -*-
"""
Created on Fri Mar 19 17:43:09 2021

@author: neurobooth
"""


import numpy as np
import math
import pylsl
import matplotlib.pyplot as plt
from pyqtgraph.Qt import QtCore, QtGui
from typing import List
import time 

# Basic parameters for the plotting window
plot_duration = 15  # how many seconds of data to show
update_interval = 100  # ms between screen updates
pull_interval = 50  # ms between each pull operation



class MarkerInlet():
    """A MarkerInlet shows events that happen sporadically as vertical lines"""
    def __init__(self, info: pylsl.StreamInfo):
        super().__init__(info)

    def pull_and_plot(self, plot_time, plttrs):
        # TODO: purge old markers
        strings, timestamps = self.inlet.pull_chunk(0)
        if timestamps:
            for plt in plttrs:
                for string, ts in zip(strings, timestamps):
                    plt.addItem(pg.InfiniteLine(ts, angle=90, movable=False, label=string[0]))



def main():
    fig, axs = plt.subplots(2,1, sharex=True)
    
    
    print("looking for streams")
    streams = pylsl.resolve_streams()

    inlets = {}
    for info in streams:    
        name = info.name() 
        inx=1
        while True:
            if name in inlets.keys():
                name = name.split("_")[0] + f"_{inx}"
            else:
                break
                
        if info.type() == 'Markers':
            print('Adding marker inlet: ' + name)
            inlets.append(MarkerInlet(info))
            
        elif info.name()  in [ "Mouse", "Audio"]:
            print('Adding data inlet: ' + name)
            
            inlet = pylsl.StreamInlet(info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
                
            inlets[name] = inlet

        else:
            print('Don\'t know what to do with stream ' + info.name())





    def update():
        tts = []
        while True:
            for nm, inlet in inlets.items():
                if nm in ['Marker', 'Markers']:
                    pass
                
                else:
                    
                    tv, ts = inlet.pull_chunk(timeout=0.0)
                    # tts.append([ts])
                    if ts == []:
                        continue
                    
                    if nm == "Mouse":
                        ax_ith = 0
                    elif nm == "Audio":
                        ax_ith = 1
                        tv = [[np.mean(t) ]for t in tv]
                    
                    
                    if not hasattr( inlet, "line"):
                        line = axs[ax_ith].plot(ts, tv)
                        inlet.line = line
                    else:
                        for chn in range(len(tv[0])):
                            inlet.line[chn].set_data(ts, tv[chn])
                            # inlet.line[chn].set_ydata(tv)
                            # inlet.line[chn].draw()    
            fig.canvas.draw()                
            fig.show()
            plt.pause(.1)



if __name__ == '__main__':
    main()