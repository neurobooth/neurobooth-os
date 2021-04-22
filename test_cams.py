# -*- coding: utf-8 -*-
"""
Created on Wed Apr 21 12:10:06 2021

@author: ACQ
"""

from time import time, sleep
from iout.camera_brio import VidRec_Brio
from iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams
import config
from iout.camera_intel import VidRec_Intel

streams = {}
#
#if len(streams):
#    print("Checking prepared devices")
#    streams = reconnect_streams(streams)
#else:
#    streams = start_lsl_threads("acquisition")            
#    streams['micro'].start()
##               streams["mbient"].start()
#print("\nDeices prepared ")

try:
    do_brio = False
    do_intel = True
    
    streams = {}
    if do_intel:
        streams["intel"] = VidRec_Intel(camindex=2)
    if do_brio:
        streams["hiFeed"] = VidRec_Brio(camindex=3 , doPreview=False)
            
        
    data =  "record:FILENAME"
    fname = config.paths['data_out'] + data.split(":")[-1] 
                
    if do_brio:
        streams["hiFeed"].start(fname)
    if do_intel:
        streams["intel"].prepare(fname)
        streams["intel"].start()
    
    print("Starting recording")
        
    sleep(5)
    
    print("Stopping")
    if do_brio:
        streams["hiFeed"].stop()
    if do_intel:
        streams["intel"].stop()
    
    print("Closing recording \n***************")
    
    
    data =  "record:FILENAME"
    fname = config.paths['data_out'] + data.split(":")[-1] 
                
    if do_brio:
        streams["hiFeed"].start(fname)
    if do_intel:
        streams["intel"].prepare(fname)
        streams["intel"].start()
    
    print("Starting recording")
        
    sleep(5)
    
    print("Stopping")
    if do_brio:
        streams["hiFeed"].stop()
    if do_intel:
        streams["intel"].stop()
    
    print("Closing recording \n***************")

except:
    print("failed")