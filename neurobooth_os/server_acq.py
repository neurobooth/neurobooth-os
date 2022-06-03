import socket
import os
import sys
from time import time, sleep
from collections import OrderedDict
import cv2
import numpy as np

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.netcomm import NewStdout, get_client_messages
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import (start_lsl_threads, close_streams,
                                             reconnect_streams, connect_mbient)
import neurobooth_os.iout.metadator as meta

def Main():
    os.chdir(neurobooth_os.__path__[0])

    sys.stdout = NewStdout("ACQ",  target_node="control", terminal_print=True)
    conn = meta.get_conn()
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    streams = {}
    lowFeed_running = False
    recording = False
    for data, connx in get_client_messages(s1):

        if "vis_stream" in data:
            if not lowFeed_running:
                lowFeed = VidRec_Brio(camindex=config.paths["cam_inx_lowfeed"],
                                      doPreview=True)
                print("LowFeed running")
                lowFeed_running = True
            else:
                print(f"-OUTLETID-:Webcam:{lowFeed.preview_outlet_id}")
                print("Already running low feed video streaming")

        elif "prepare" in data:
            # data = "prepare:collection_id:str(log_task_dict)"
            collection_id = data.split(":")[1]
            log_task = eval(data.replace(f"prepare:{collection_id}:", ""))
            subject_id_date = log_task['subject_id-date']
            ses_folder = f"{config.paths['data_out']}{subject_id_date}"
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)
            if len(streams):
                # print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("acquisition", collection_id, conn=conn)

            devs = list(streams.keys())
            print("UPDATOR:-Connect-")

        elif "frame_preview" in data and not recording:
            if not any("IPhone" in s for s in streams):
                print('no iphone')
                connx.send("ERROR: no iphone in LSL streams".encode("ascii"))
                continue

            frame = streams[[i for i in streams if 'IPhone' in i][0]].frame_preview()
            frame_prefix=b'::BYTES::'+str(len(frame)).encode('utf-8')+b'::'
            frame=frame_prefix+frame
            connx.send(frame)

        elif "record_start" in data:  
            # "record_start::filename::task_id" FILENAME = {subj_id}_{obs_id}
            print("Starting recording")
            fname, task = data.split("::")[1:]  
            fname = f"{config.paths['data_out']}{subject_id_date}/{fname}"

            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]: 
                    if task_devs_kw[task].get(k):
                        streams[k].start(fname)
            
            for k in streams.keys():
                if  "Mic_Yeti" in k:
                    streams[k].start()
                    
            msg = "ACQ_devices_ready"
            connx.send(msg.encode("ascii"))
            recording = True

        elif "record_stop" in data:
            # print("Closing recording")
            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                    if task_devs_kw[task].get(k):
                        streams[k].stop()
                        
            for k in streams.keys():
                if  "Mic_Yeti" in k:
                    streams[k].stop()
                    
            msg = "ACQ_devices_stoped"
            connx.send(msg.encode("ascii"))
            recording = False

        elif data in ["close", "shutdown"]:
            if "shutdown" in data:
                sys.stdout = sys.stdout.terminal
                s1.close()
                
            streams = close_streams(streams)

            if "shutdown" in data:
                if lowFeed_running:
                    lowFeed.close()
                    lowFeed_running = False
                    print("Closing RTD cam")
                break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            connx.send(msg.encode("ascii"))

        else:
            print(data)

Main()
