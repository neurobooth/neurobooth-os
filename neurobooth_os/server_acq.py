import socket
import os
import sys
from time import time, sleep

from neurobooth_os import config
from neurobooth_os.netcomm import (socket_message, NewStdout, get_client_messages)
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import (start_lsl_threads, close_streams,
                                             reconnect_streams, connect_mbient)


def Main():

    sys.stdout = NewStdout("ACQ",  target_node="control", terminal_print=True)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    streams = {}
    lowFeed_running = False
    for data, conn in get_client_messages(s1):

        if "vis_stream" in data:
            if not lowFeed_running:
                lowFeed = VidRec_Brio(camindex=config.cam_inx["lowFeed"],
                                      doPreview=True)
                print("LowFeed running")
                lowFeed_running = True
            else:
                print(f"-OUTLETID-:Webcam:{lowFeed.preview_outlet_id}")
                print("Already running low feed video streaming")

        elif "prepare" in data:
            # data = "prepare:collection_id:str(tech_obs_log_dict)"
            collection_id = data.split(":")[1]
            if len(streams):
                print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("acquisition", collection_id)

            devs = list(streams.keys())
            print("UPDATOR:-Connect-")

        elif "dev_param_update" in data:
            None

        elif "record_start" in data:  
            # "record_start:FILENAME" FILENAME = {subj_id}_{task}
            print("Starting recording")
            fname = config.paths['data_out'] + data.split(":")[-1]
            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
                    streams[k].start(fname)
            msg = "ACQ_ready"
            conn.send(msg.encode("ascii"))
            print("ready to record")

        elif "record_stop" in data:
            print("Closing recording")
            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
                    streams[k].stop()

        elif data in ["close", "shutdown"]:
            print("Closing devices")
            streams = close_streams(streams)

            if "shutdown" in data:
                if lowFeed_running:
                    lowFeed.close()
                    lowFeed_running = False
                print("Closing RTD cam")
                break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            conn.send(msg.encode("ascii"))

        else:
            print(data)

    sleep(.5)
    s1.close()
    sys.stdout = sys.stdout.terminal


Main()
