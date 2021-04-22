# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""

def start_lsl_threads(node_name):    
    streams = {}    
    if node_name == "acquisition":
        from iout.microphone import MicStream
        from iout.camera_brio import VidRec_Brio
        from iout.camera_intel import VidRec_Intel
        from iout.mbient import Sensor
        
        streams["hiFeed"] = VidRec_Brio(camindex=3 , doPreview=False)
        streams['micro'] = MicStream()
        streams["intel"] = VidRec_Intel(camindex=2)
        
        mac = "CE:F3:BD:BD:04:8F"
#        streams["mbient"] = Sensor(mac)
       
    elif node_name == "presentation":     
        from iout.marker import marker_stream       
        from iout.mouse_tracker  import MouseStream
        
        streams['mouse'] = MouseStream()
        streams['marker'] =  marker_stream()
        
    return streams

def close_streams(streams, cams=False):
    for k in list(streams):
        print(f"Closing {k} stream")
        if cams and k in ["hiFeed", "intel"]:
            streams[k].close()
        else:
            streams[k].stop()
        del streams[k]
    return streams



def reconnect_streams(streams, cams=False):
    for k in list(streams): 
        if k in ["hiFeed", "intel"]:
            continue
        
        if not streams[k].streaming:
            print(f"Re-streaming {k} stream")
            streams[k].start()       
        
    return streams
