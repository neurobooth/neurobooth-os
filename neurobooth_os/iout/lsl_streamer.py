# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""
from neurobooth_os import config
from neurobooth_os.iout import metadator as meta


def start_lsl_threads(node_name, collection_id="mvp_025", win=None):    
    streams = {}    
    if node_name == "acquisition":
        from iout.microphone import MicStream
        from iout.camera_brio import VidRec_Brio
        from iout.camera_intel import VidRec_Intel
        from iout.ximea_cam import VidRec_Ximea
        
        kward_devs = meta.get_kwarg_collection(collection_id)
        
        streams['micro'] = MicStream()
        for kdev, argsdev in kward_devs.items():
            if "Intel" in kdev:
                streams[kdev] = VidRec_Intel(**argsdev)
            elif "Mbient" in kdev:
                print(kdev)
               
                streams[kdev] = connect_mbient(**argsdev)
                if streams[kdev] is None:
                    del streams[kdev]
                    
       
    elif node_name == "presentation":     
        from iout.marker import marker_stream       
        from iout.mouse_tracker  import MouseStream
        from iout.eyelink_tracker import EyeTracker
        
        streams['mouse'] = MouseStream()
        streams['marker'] =  marker_stream()
        streams['eye_tracker'] = EyeTracker(win=win)
        
    return streams


def connect_mbient(dev_name="LH", mac='CE:F3:BD:BD:04:8F', try_nmax=5, **kwarg):
    from iout.mbient import Sensor
    
       
    tinx = 0
    print(f"Trying to connect mbient {dev_name}, mac {mac}")
    while True:        
        try:            
          
            sens = Sensor( mac, dev_name, **kwarg)
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
        if cams and any([True for d in  ["hiFeed", "Intel", "ximea"] if d in k]):
            streams[k].close()
        else:
            streams[k].stop()
        del streams[k]
    return streams


def reconnect_streams(streams):
    for k in list(streams): 
        if any([True for d in  ["hiFeed", "Intel", "ximea"] if d in k]):
            continue
        
        if not streams[k].streaming:
            print(f"Re-streaming {k} stream")
            streams[k].start()
        print(f"-OUTLETID-:{k}:{streams[k].oulet_id}")
        
    return streams


