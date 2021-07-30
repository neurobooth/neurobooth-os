# -*- coding: utf-8 -*-
"""
Created on Fri Mar 19 17:43:09 2021

@author: Adonay
"""

import numpy as np
import pylsl
import matplotlib.pyplot as plt
import matplotlib
import cv2
import threading
import time


def update_streams():
    streams = pylsl.resolve_streams(.6) 
    inlets= {}
    for info in streams:            
        name = info.name()     
        # inx=1
        # while True:
        #     if name in inlets.keys():
        #         name = name.split("_")[0] + f"_{inx}"
        #         inx +=1
        #     else:  
        #         break
                
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


def update_streams_fromID(stream_ids):
    # stream_ids = dict with streams uuids
    
    streams = []
    for id_stream in  stream_ids.values():
        print("resolving: ", id_stream)
        streams += pylsl.resolve_byprop("source_id", id_stream, timeout=10)
    
    inlets= {}
    for info in streams:  
        
        name = info.name()     
        print("outlet name: ", name)  
        if info.type() == 'Markers':
            print('(NOT YET) Adding marker inlet: ' + name)
            # inlets.append(MarkerInlet(info))
            
        elif info.name()  in ["Screen", "Webcam", "Mouse", "Audio", "mbient", "EyeLink"]:
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
        inlet.flush()
        
    return  plot_elem        


class stream_plotter():
    
    def __init__(self, plt_img=False, plt_ts=True):
         
        self.inlets = {}
        self.plt_img= plt_img
        self.plt_ts = plt_ts
        self.pltotting_img = False
        self.pltotting_ts =  False
    
    def start(self, inlets):
        if any([self.pltotting_img, self.pltotting_ts]):
            self.stop()
            
        self.pltotting_img =  self.plt_img
        self.pltotting_ts =  self.plt_ts
        
        self.inlets = inlets
        
        if self.plt_img is True and any([k for k in ['Mouse',"mbient", "Audio"] if k in inlets.keys()]):
            self.thread_img = threading.Thread(target=self.update_imgs, daemon=True)               
            self.thread_img.start()

        if self.plt_ts is True and any([k for k in ['Mouse',"mbient", "Audio"] if k in inlets.keys()]):  
            self.thread_ts = threading.Thread(target=self.update_ts, daemon=True)        
            self.thread_ts.start()
        else:
            self.pltotting_ts =  False
            
        
        
        
    def stop(self):    
        self.pltotting_img = False
        self.pltotting_ts =  False
        self.inlets = {}
        print("Closed plotting windows")
        

    def update_ts(self):
        plt.ion()
        fig, axs = plt.subplots(3,1, sharex=False, figsize=(9.16,  9.93))
        axs[-1].set_xticks([])
        mngr = plt.get_current_fig_manager()
        mngr.window.setGeometry(1015,30,905, 1005)
        fig.tight_layout()
        fig.canvas.draw()                
        fig.show()
        plt.show(block=False)
        
        sampling = .1
        buff_size = 1024
        mypause(sampling)
        
        while self.pltotting_ts:
            
            # frame_ts = []
            for nm, inlet in self.inlets.items():
                if nm in ['Marker', 'Markers']:
                    continue
                    
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
            
 
            mypause(sampling)
            if len(self.inlets)== 0:
                self.pltotting_ts = False
                break
            # time.sleep(.1)
            
        self.pltotting_ts = False
        plt.close(fig)  
    
    
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

            
            frames = cv2.hconcat(frame_queue_cam), cv2.hconcat(frame_queue_scr)
            frames = cv2.vconcat(frames)

            cv2.imshow("Output Frame", frames)

            key = cv2.waitKey(1) & 0xFF
            if key == ord:
                break
                
        cv2.DestroyWindow("Output Frame")
    
    

def mypause(interval):
    backend = plt.rcParams['backend']
    if backend in matplotlib.rcsetup.interactive_bk:
        figManager = matplotlib._pylab_helpers.Gcf.get_active()
        if figManager is not None:
            canvas = figManager.canvas
            if canvas.figure.stale:
                canvas.draw()
            canvas.start_event_loop(interval)
            # return

if 0:
    ppt = stream_plotter(plt_img=True, plt_ts=True)
    ppt.start()
    
    if 0: 
        ppt.stop()
# ppt.update_ts()
