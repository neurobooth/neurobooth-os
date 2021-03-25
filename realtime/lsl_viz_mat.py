# -*- coding: utf-8 -*-
"""
Created on Fri Mar 19 17:43:09 2021

@author: neurobooth
"""


import numpy as np
import math
import pylsl
import matplotlib.pyplot as plt
import cv2
from typing import List
import time 

# # Basic parameters for the plotting window
# plot_duration = 15  # how many seconds of data to show
# update_interval = 100  # ms between screen updates
# pull_interval = 50  # ms between each pull operation



# class MarkerInlet():
#     """A MarkerInlet shows events that happen sporadically as vertical lines"""
#     def __init__(self, info: pylsl.StreamInfo):
#         super().__init__(info)

#     def pull_and_plot(self, plot_time, plttrs):
#         # TODO: purge old markers
#         strings, timestamps = self.inlet.pull_chunk(0)
#         if timestamps:
#             for plt in plttrs:
#                 for string, ts in zip(strings, timestamps):
#                     plt.addItem(pg.InfiniteLine(ts, angle=90, movable=False, label=string[0]))



# def main():
# fig, axs = plt.subplots(4,1)#, sharex=True)

fig, axs = plt.subplots(1,1)#

axs.set_xticks([])
axs.set_yticks([])

img = axs.imshow(np.zeros((480, 640)), cmap="gray")
img.set_interpolation("nearest")
img.autoscale()
 
 
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
        # inlets.append(MarkerInlet(info))
        
    elif info.name()  in [ "Mouse", "Audio", "mbient", "Screen"]:
        print('Adding data inlet: ' + name)
        
        inlet = pylsl.StreamInlet(info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
            
        inlets[name] = inlet

    else:
        print('Don\'t know what to do with stream ' + info.name())



    
    
    # def update():
sampling = .1
buff_size = 1024
while True:
    lims = []
    for nm, inlet in inlets.items():
        if nm in ['Marker', 'Markers']:
            continue
        
        elif nm in ['Mouse', "Audio", "mbient"]:
            
            tv, ts = inlet.pull_chunk(timeout=0.0)
            # tts.append([ts])
            if ts == []:
                continue
            
            lims.append(max(ts))
            
            if nm == "Mouse":
                ax_ith = 0
            elif nm == "mbient":
                ax_ith = 1
                tv = [[np.mean(t[:3]), np.mean(t[3:])] for t in tv]
                
            elif nm == "Audio":
                ax_ith = 2
                tv = [[np.mean(t) ]for t in tv]
                
            
            tv = np.array(tv)
            ts = np.array(ts)
            
            sz = ts.shape[0] 
            
            if not hasattr( inlet, "line"):
                inlet.xdata = np.array(range(buff_size))
                inlet.ydata = np.zeros((buff_size, tv.shape[1]))
    
                inlet.line = axs[ax_ith].plot(inlet.xdata, inlet.ydata)
        
             
            inlet.ydata = np.vstack((inlet.ydata[sz - buff_size:-1, :], tv))
            
            inlet.xdata = np.hstack((inlet.xdata[sz - buff_size:-1], ts))
            
            for i, chn in enumerate(inlet.ydata.T):
                inlet.line[i].set_data(inlet.xdata, chn)
                
            axs[ax_ith].set_xlim([ max(ts) - (sampling*50) , max(ts)])
            ylim = inlet.ydata.flatten()
            axs[ax_ith].set_ylim([ min(ylim) , max(ylim)])
            
        elif nm == "Screen":
            # 
            tv, ts = inlet.pull_sample(timeout=0.0)
            
            # tv, ts = inlet.pull_chunk(timeout=0.0)
            
            if ts == [] or ts is None:
                
                continue
            
            # print(f"frame {tv[-1][0]}")
            
            # tv = tv[-1][1:]
            
            print(f"frame {tv[0]}")
            
            tv = tv[1:]
            img_frame = np.array(tv, dtype=np.uint8).reshape(480, 640)
            cv2.imshow("Output Frame", img_frame)
            # img.set_data(img_frame)
            # img.autoscale()
            # axs[3].imshow(img_frame,  cmap='gray')
            # axs.imshow(img_frame,  cmap='gray')
            # check for 'q' key if pressed
            key = cv2.waitKey(1) & 0xFF
            if key == ord:
                break
            
            
    # if lims != []:            
    #     axs[1].set_xlim([ max(lims) - (sampling*100) , max(lims)])
    
    # fig.canvas.draw()                
    # fig.show()
    # plt.pause(.1)



# if __name__ == '__main__':
#     main()
>>>>>>> 054a9c28e55a5db1f032783eeca11b80b6eb6890
