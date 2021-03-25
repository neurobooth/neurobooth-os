# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""

import threading
from iout.mouse_tracker  import MouseStream
from iout.microphone import MicStream
from iout.camera_brio import VidRec_Brio
from iout.screen_capture import ScreenStream


def start_lsl_threads():
    streams = {}
    streams['mouse'] = MouseStream()
    streams['micro'] = MicStream()
    streams['screen'] = ScreenStream()
    
    
    # streams['eye_tracker'] = threading.Thread(target=tobii_stream) 
    strm_vids = cameras_stream()
    for ix, cam in enumerate(strm_vids):
        streams[f'cam_{ix}'] = cam 
        

    
    streams['strm_vids']= strm_vids
    
    return streams

def close_threads(streams):
    
    for vid in streams['strm_vids']:
        vid.recording = False
        
        