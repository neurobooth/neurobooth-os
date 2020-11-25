# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""
import threading

from mouse_tracker  import mouse_stream
from microphone import audio_stream
from camera_recorder import cameras_stream, cameras_start_rec


strm_mouse = threading.Thread(target=mouse_stream)
strm_micro =  threading.Thread(target=audio_stream)
strm_vids = cameras_stream()

strm_mouse.start()
strm_micro.start()
vcaps = cameras_start_rec(strm_vids)

