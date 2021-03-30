# -*- coding: utf-8 -*-
"""
Created on Fri Mar 19 17:43:09 2021

@author: Adonay
"""

import numpy as np
import pylsl
import matplotlib.pyplot as plt
import cv2
import threading



def stream_plotter():
     
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
            
        elif info.name()  in [ "Mouse", "Audio", "mbient"]:
            print('Adding data inlet: ' + name)
            
            inlet = pylsl.StreamInlet(info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
            inlets[name] = inlet
    
        else:
            print('Don\'t know what to do with stream ' + info.name())
    
    
    thread_img =  threading.Thread(target=update_imgs, args=[inlets])
    thread_ts =  threading.Thread(target=update_ts, args=[inlets])
    
    thread_img.start()
    thread_ts.start()
    
    return thread_img, thread_ts


def update_imgs(inlets):   
        
    frame_screen, frame_cam = np.ones((240, 320), dtype=np.uint8), np.ones((240, 320), dtype=np.uint8)
        
    while True:     
        for nm, inlet in inlets.items():
            if nm in ['Marker', 'Markers']:
                continue
                
            elif nm == "Screen":
                
                tv, ts = inlet.pull_sample(timeout=0.0)                 
                if ts == [] or ts is None:
                    continue
                            
                tv = tv[1:]  # First element is frame number
                frame_screen = np.array(tv, dtype=np.uint8).reshape(240, 320)
    
            elif nm == "Webcam":
                
                tv, ts = inlet.pull_sample(timeout=0.0)                
                if ts == [] or ts is None:
                    continue
    
                frame_cam = np.array(tv, dtype=np.uint8).reshape(240, 320)
          
                        
            final_frame = cv2.vconcat([frame_screen, frame_cam] )
            cv2.imshow("Output Frame", final_frame)
    
            key = cv2.waitKey(1) & 0xFF
            if key == ord:
                break
           


def update_ts(inlets):
    
    fig, axs = plt.subplots(3,1)#, sharex=True)
    
    sampling = .1
    buff_size = 1024
    while True:

        for nm, inlet in inlets.items():
            if nm in ['Marker', 'Markers']:
                continue
            
            elif nm in ['Mouse', "Audio", "mbient"]:
                
                tv, ts = inlet.pull_chunk(timeout=0.0)
    
                if ts == []:
                    continue
                
                    
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
                
                
            fig.canvas.draw()                
            fig.show()
            plt.pause(.1)  
            
            

              


     
if __name__ == "__main__":
    
    threads = stream_plotter()


