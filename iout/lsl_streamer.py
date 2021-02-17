# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""

import threading
from iout.mouse_tracker  import mouse_stream
from iout.microphone import audio_stream
from iout.camera_recorder2 import cameras_stream, cameras_start_rec
from iout.eye_tracker import tobii_stream


def start_lsl_threads():
    streams = {}
    streams['mouse'] = threading.Thread(target=mouse_stream)
    streams['micro'] = threading.Thread(target=audio_stream)
    # streams['eye_tracker'] = threading.Thread(target=tobii_stream) 
    strm_vids = cameras_stream()
    for ix, cam in enumerate(strm_vids):
        streams[f'cam_{ix}'] = cam 
        
    streams['mouse'].start()
    streams['micro'].start()
    # streams['eye_tracker'].start()
    
    streams['strm_vids']= strm_vids
    
    return streams

def close_threads(streams):
    
    for vid in streams['strm_vids']:
        vid.recording = False
        
        