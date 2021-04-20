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
import time


def update_streams():
    streams = pylsl.resolve_streams() 
    inlets= {}
    for info in streams:            
        name = info.name()     
        inx=1
        while True:
            if name in inlets.keys():
                name = name.split("_")[0] + f"_{inx}"
                inx +=1
            else:  
                break
                
        if info.type() == 'Markers':
            print('(NOT YET) Adding marker inlet: ' + name)
            # inlets.append(MarkerInlet(info))
            
        elif info.name()  in ["Screen", "Webcam", "Mouse", "Audio", "mbient"]:
            print('Adding data inlet: ' + name)
            
            inlet = pylsl.StreamInlet(info)#, recover=False)
            inlets[name] = inlet
    
        else:
            print('Don\'t know what to do with stream ' + info.name())
    return inlets



def get_lsl_images(inlets, frame_sz=(320, 240)):   
    plot_elem = []
    for nm, inlet in inlets.items():        
        tv, ts = inlet.pull_sample(timeout=0.0)
        if ts == [] or ts is None:
             continue
         
        if nm not in ["Screen", "Webcam"]:
            continue
                      
        if nm == "Screen":               
            tv = tv[1:]  
          
        frame = np.array(tv, dtype=np.uint8).reshape(frame_sz[1], frame_sz[0])
        imgbytes = cv2.imencode('.png', frame)[1].tobytes()        
        plot_elem.append([nm, imgbytes])
        
    return  plot_elem        

class stream_plotter():
    
    def __init__(self, plt_img=False, plt_ts=True):
         
        self.inlets = {}
        self.plt_img= plt_img
        self.plt_ts = plt_ts
        
    
    def start(self):

        self.pltotting_img =  self.plt_img
        self.pltotting_ts =  self.plt_ts
        
        self.scann()
        
        if self.plt_img is True:
            # self.update_imgs()
            self.thread_img = threading.Thread(target=self.update_imgs)               
            self.thread_img.start()

        if self.plt_ts is True:   
            self.thread_ts = threading.Thread(target=self.update_ts)        
            self.thread_ts.start()
        
        
        
    def stop(self):    
        self.pltotting_img = False
        self.pltotting_ts =  False
        print("Closeing plotting windows")
        
        
    def scann(self):
        print("looking for streams")
        streams = pylsl.resolve_streams() 
        
        self.inlets = {}
        for info in streams:    
            
            name = info.name() 
    
            inx=1
            while True:
                if name in self.inlets.keys():
                    name = name.split("_")[0] + f"_{inx}"
                else:
                    break
                    
            if info.type() == 'Markers':
                print('(NOT YET) Adding marker inlet: ' + name)
                # inlets.append(MarkerInlet(info))
                
            elif info.name()  in ["Screen", "Webcam", "Mouse", "Audio", "mbient"]:
                print('Adding data inlet: ' + name)
                
                inlet = pylsl.StreamInlet(info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
                self.inlets[name] = inlet
        
            else:
                print('Don\'t know what to do with stream ' + info.name())
    
      
    
    
    def update_imgs(self):   
            
        frame_screen, frame_cam = np.ones((240, 320), dtype=np.uint8), np.ones((240, 320), dtype=np.uint8)
        
        nqueue  = 10
        frame_queue_scr, frame_queue_cam =  [], []
        for n in range(nqueue):
            frame_queue_scr.append(frame_screen)
            frame_queue_cam.append(frame_cam)
            
        # cv2.namedWindow("Output Frame")  
        
        while self.pltotting_img:     
            for nm, inlet in self.inlets.items():

                if nm in ['Marker', 'Markers']:
                    continue
                    
                elif nm == "Screen":
                    tv, ts = inlet.pull_sample(timeout=0.0)                 
                    if ts == [] or ts is None:
                        continue
           
                    tv = tv[1:]  # First element is frame number
                    frame_screen = np.array(tv, dtype=np.uint8).reshape(240, 320)
                    
                    frame_queue_scr.pop(0)
                    frame_queue_scr.append(frame_screen)
                                        
                elif nm == "Webcam":
                    tv, ts = inlet.pull_sample(timeout=0.0)                
                    if ts == [] or ts is None:
                        continue

                    frame_cam = np.array(tv, dtype=np.uint8).reshape(240, 320)
                    
                    frame_queue_cam.pop(0)
                    frame_queue_cam.append(frame_cam)

            # final_frame = cv2.vconcat([frame_screen, frame_cam] )
            # cv2.imshow("Output Frame", final_frame)
            
            # key = cv2.waitKey(1) & 0xFF
            # if key == ord:
            #     break
            
            frames = cv2.hconcat(frame_queue_cam), cv2.hconcat(frame_queue_scr)
            frames = cv2.vconcat(frames)

            cv2.imshow("Output Frame", frames)

            key = cv2.waitKey(1) & 0xFF
            if key == ord:
                break
                
        # cv2.DestroyWindow("Output Frame")
    
    
    def update_ts(self):
        
        fig, axs = plt.subplots(3,1, sharex=True)
        
        sampling = .1
        buff_size = 1024
        while self.pltotting_ts:
            
            frame_ts = []
            for nm, inlet in self.inlets.items():
                if nm in ['Marker', 'Markers']:
                    continue
                
                elif nm == "Screen":
                                        
                    tv, ts = inlet.pull_sample(timeout=0.0)                 
                    if ts == [] or ts is None:
                        continue
           
                    frame_ts = ts
                    
                    
                elif nm in ['Mouse',"mbient", "Audio"]:                    
                    tv, ts = inlet.pull_chunk(timeout=0.0)
        
                    if ts == []:
                        continue                    
                        
                    clicks =[]
                    if nm == "Mouse":
                        ax_ith = 0
                        clicks = [[tt,t[-1]] for t, tt in zip(tv, ts)if t[-1]!=0]
                        tv = [t[:-1] for t in tv]
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
                    
                    if clicks != []:
                        for clk in clicks:
                            clr = "g" if clk[1]==1 else "r" if clk[1]==-1 else "k"
                            axs[ax_ith].axvline(x=clk[0], color=clr)
                            
                    axs[ax_ith].set_xlim([ max(ts) - (sampling*50) , max(ts)])
                    ylim = inlet.ydata.flatten()
                    axs[ax_ith].set_ylim([ min(ylim) , max(ylim)])
            
            if frame_ts != []:
                for ax in axs:
                    ax.axvline(frame_ts, color="b", alpha=.3, linestyle='--')
       
            fig.canvas.draw()                
            fig.show()
            plt.pause(sampling) 
            # time.sleep(.1)
                
                
        plt.close(fig)


if 0:
    ppt = stream_plotter(plt_img=True, plt_ts=True)
    ppt.start()
    
    if 0: 
        ppt.stop()
# ppt.update_ts()
