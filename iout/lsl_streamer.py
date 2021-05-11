# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""
import config

def start_lsl_threads(node_name):    
    streams = {}    
    if node_name == "acquisition":
        from iout.microphone import MicStream
        from iout.camera_brio import VidRec_Brio
        from iout.camera_intel import VidRec_Intel

        
        streams["hiFeed"] = VidRec_Brio(camindex=0 , doPreview=False)
        streams['micro'] = MicStream()
        streams["intel"] = VidRec_Intel(camindex=3)
        
        mbient_name = 'RH'
        streams["mbient"] = connect_mbient(mbient_name)
       
    elif node_name == "presentation":     
        from iout.marker import marker_stream       
        from iout.mouse_tracker  import MouseStream
        
        streams['mouse'] = MouseStream()
        streams['marker'] =  marker_stream()
        
    return streams


def connect_mbient(dev_name="RH", try_nmax=5):
    from iout.mbient import Sensor
    
    mac = config.mbient_macs[dev_name]
    
    tinx = 0
    while True:
        try:
            print(f"Trying to connect mbient {dev_name}")
            sens = Sensor(mac)
            return sens 
        except:        
            print(f"Trying to connect mbient {dev_name}, {tinx} out of {try_nmax} tries")
            tinx += 1
            if tinx >= try_nmax:
                print(f"Failed to connect mbient {dev_name}")
                break    


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
        print(f"-OUTLETID-:{k}:{streams[k].oulet_id}")
        
    return streams

