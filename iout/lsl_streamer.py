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

        
        streams["hiFeed1"] = VidRec_Brio(camindex=config.cam_inx["brio1"] , doPreview=False)
        streams["hiFeed2"] = VidRec_Brio(camindex=config.cam_inx["brio2"] , doPreview=False)
        streams["intel1"] = VidRec_Intel(camindex=config.cam_inx["intel1"])
        streams["intel2"] = VidRec_Intel(camindex=config.cam_inx["intel2"])
        streams["intel3"] = VidRec_Intel(camindex=config.cam_inx["intel3"])
        streams['micro'] = MicStream()
        
        
        mbient_name = 'RH'
        streams["mbient"] = connect_mbient(mbient_name)
        if streams["mbient"] is None:
            del streams["mbient"]
       
    elif node_name == "presentation":     
        from iout.marker import marker_stream       
        from iout.mouse_tracker  import MouseStream
        
        streams['mouse'] = MouseStream()
        streams['marker'] =  marker_stream()
        
    return streams


def connect_mbient(dev_name="LF", try_nmax=5):
    from iout.mbient import Sensor
    
    mac = config.mbient_macs[dev_name]
    
    tinx = 0
    print(f"Trying to connect mbient {dev_name}, mac {mac}")
    while True:        
        try:            
            sens = Sensor(mac, dev_name)
            return sens 
        except Exception as e:        
            print(f"Trying to connect mbient {dev_name}, {tinx} out of {try_nmax} tries {e}")
            tinx += 1
            if tinx >= try_nmax:
                print(f"Failed to connect mbient {dev_name}")
                break    


def close_streams(streams, cams=False):
    for k in list(streams):
        print(f"Closing {k} stream")
        if cams and k[:-1] in ["hiFeed", "intel", "mbient"]:
            streams[k].close()
        else:
            streams[k].stop()
        del streams[k]
    return streams


def reconnect_streams(streams, cams=False):
    for k in list(streams): 
        if k[:-1] in ["hiFeed", "intel"]:
            continue
        
        if not streams[k].streaming:
            print(f"Re-streaming {k} stream")
            streams[k].start()
        print(f"-OUTLETID-:{k}:{streams[k].oulet_id}")
        
    return streams

