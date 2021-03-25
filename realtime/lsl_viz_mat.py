# -*- coding: utf-8 -*-
"""
Created on Fri Mar 19 17:43:09 2021

@author: neurobooth
"""

import numpy as np
import pylsl
import matplotlib.pyplot as plt
import cv2
import threading


def main():
     
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
            print('(NOT YET) Adding marker inlet: ' + name)
            # inlets.append(MarkerInlet(info))
            
        elif info.name()  in [ "Mouse", "Audio", "mbient", "Screen", "Webcam"]:
            print('Adding data inlet: ' + name)
            
            inlet = pylsl.StreamInlet(info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
            inlets[name] = inlet
    
        else:
            print('Don\'t know what to do with stream ' + info.name())
    
        
        update(inlets)        


def update(inlets):
    
    fig, axs = plt.subplots(3,1)#, sharex=True)
    
    frame_screen, frame_cam = np.zeros((240, 320), dtype=np.uint8), np.zeros((240, 320), dtype=np.uint8)
    
    sampling = .1
    buff_size = 1024
    while True:
        lims = []
        for nm, inlet in inlets.items():
            if nm in ['Marker', 'Markers']:
                continue
            
            elif nm in ['Mouse', "Audio", "mbient"]:
                
                tv, ts = inlet.pull_chunk(timeout=0.0)
    
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
                
                tv, ts = inlet.pull_sample(timeout=0.0) 
                
                if ts == [] or ts is None:
                    continue
                            
                tv = tv[1:]
                frame_screen = np.array(tv, dtype=np.uint8).reshape(240, 320)
    
            elif nm == "Webcam":
                
                tv, ts = inlet.pull_sample(timeout=0.0)
                
                if ts == [] or ts is None:
                    continue
    
                frame_cam = np.array(tv, dtype=np.uint8).reshape(240, 320)
                
            fig.canvas.draw()                
            fig.show()
            
            final_frame = cv2.hconcat([frame_screen, frame_cam] )
            cv2.imshow("Output Frame", final_frame)
    
            key = cv2.waitKey(100) & 0xFF
            if key == ord:
                break
                
            
    # if lims != []:            
    #     axs[1].set_xlim([ max(lims) - (sampling*100) , max(lims)])
    
    # fig.canvas.draw()                
    # fig.show()
    # plt.pause(.1)
    
if __name__ == "__main__":
    
    main()
    # t = threading.Thread(target=main)
    # t.start()

