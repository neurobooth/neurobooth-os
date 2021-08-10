# -*- coding: utf-8 -*-
"""
Created on Mon Mar 15 11:40:01 2021

@author: neurobooth
"""

from vidgear.gears import ScreenGear
import cv2
# import pyautogui
import win32gui
import numpy as np
from pylsl import StreamInfo, StreamOutlet
import time
import threading
import uuid

class ScreenMirror():
    def __init__(self, Fps=1, res=(320, 240), options=None, RGB=False, local_plot=False):
        """
        parameters:
            Fps : Int
                Rate screen is capturesd
            options : dict | None
                define dimensions of screen w.r.t to given monitor to be captured
            RGB : Bool
                If True colored screen is catured, else grey
            Local_plot : Bool
                To show screen capture locally with a window figure
            
        """
        
        if options is None:
            self.options = {"top": 0, "left": 0, "width": 1920, "height": 1080}
        else:
            self.options = options
            
        self.Xs = [0,8,6,14,12,4,2,0]
        self.Ys = [0,2,4,12,14,6,8,0]
        self.fps = Fps
        self.res = res
        self.RGB = RGB
        self.local_plot = local_plot    
        
        self.streaming = False
        
        # Setup outlet stream info
        xy = self.options["width"] * self.options["height"]
        xy = res[0]*res[1] 
        if RGB is True:
            xy = xy*3 
        xy += 1
        
        self.oulet_id =  str(uuid.uuid4())
        info_stream = StreamInfo(name='Screen', type='Experimental',
                                       # nominal_srate=self.fps, 
                                       channel_count=xy,
                                       channel_format='float32', source_id=self.oulet_id
                                       )  
        self.info_stream = info_stream
        self.outlet_screen = StreamOutlet(info_stream)
        print(f"-OUTLETID-:Screen:{self.oulet_id}")

                        
    def start(self):
        self.streaming = True
            
        self.stream_thread = threading.Thread(target=self.stream)
        self.stream_thread.start()
        
    def stream(self):
        # open video stream with defined parameters        
        self.screen= ScreenGear(logging=False, **self.options)
        self.screen.start()
        self.inx = 0   
        
        if self.local_plot:
             cv2.namedWindow('Screen', cv2.WINDOW_AUTOSIZE)
             
        tic = time.time()
        # loop over
        while self.streaming == True:
            # read frames from stream
            frame = self.screen.read()
            # check for frame if Nonetype
            if frame is None:
                break
            
            # mouseX, mouseY = pyautogui.position()
            mouseX, mouseY = win32gui.GetCursorPos()
            
            
            if self.RGB is not True:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)            
            else:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)        
             
            # Synthesize mouse pointer
            Xthis = [4 * x + mouseX for x in self.Xs]
            Ythis = [4 * y + mouseY for y in self.Ys]
            points = list(zip(Xthis, Ythis))
            points = np.array(points, 'int32')
            cv2.fillPoly(frame, [points], color=[255, 0, 0])
                                        
            frame = cv2.resize(frame,self.res)
            
            self.inx += 1            
            f = np.insert(frame.flatten(), 0, self.inx)     
            
            try:
                self.outlet_screen.push_sample(f)
            except:  # "OSError" from C++
                print("Reopening stream already closed")
                self.outlet_screen = StreamOutlet(self.info_stream)
                self.outlet_screen.push_sample(f)
                
            if self.local_plot:
                # Show output window
                cv2.imshow("Screen", frame)
                # check for 'q' key if pressed
                key = cv2.waitKey(1) & 0xFF# int(1/self.fps)*100) & 0xFF
                if key == ord("q"):
                    break
                
            # time.sleep(1/self.fps)s
 
    def stop(self):
        # safely close video stream
        try:
            self.screen.stop()
        except AttributeError:
            print("Never started to capture screen")
                  
        self.streaming = False
        self.outlet_screen.__del__()
        if self.local_plot:
            cv2.destroyAllWindows()
