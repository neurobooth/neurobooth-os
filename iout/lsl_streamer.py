# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""

from iout.mouse_tracker  import MouseStream
from iout.microphone import MicStream
from iout.camera_brio import VidRec_Brio
from iout.marker import marker_stream


def start_lsl_threads(node_name):
    
    streams = {}
    
    if node_name == "acquisition":
        streams["hiFeed"] = VidRec_Brio(camindex=1, doPreview=False)
        streams['micro'] = MicStream()
       
    elif node_name == "presentation":       
        streams['mouse'] = MouseStream()
        streams['marker'] =  marker_stream()
        
    return streams

def close_threads(streams):
    
    for vid in streams['strm_vids']:
        vid.recording = False
        
        