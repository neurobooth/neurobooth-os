import socket, os
import io
import sys
from time import time, sleep
from neurobooth_os import config

from neurobooth_os.netcomm.client import socket_message
from neurobooth_os.netcomm.server import get_client_messages, get_fprint
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient

os.chdir(r'C:\neurobooth-eel\neurobooth_os\\')



def Main():

        fprint, send_stdout, old_stdout = get_fprint()
        s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        for data in get_client_messages(s1, fprint, old_stdout):

            if "vis_stream" in data:
                if not lowFeed_running:
                    lowFeed = VidRec_Brio(camindex=config.cam_inx["lowFeed"],
                                          doPreview=True)
                    fprint ("LowFeed running")
                    lowFeed_running = True
                else:
                    fprint(f"-OUTLETID-:Webcam:{lowFeed.preview_outlet_id}")
                    fprint ("Already running low feed video streaming")

            elif "prepare" in data:
                # data = "prepare:collection_id:str(tech_obs_log_dict)"
                collection_id = data.split(":")[1]
                if len(streams):
                    fprint("Checking prepared devices")
                    streams = reconnect_streams(streams)
                else:
                    streams = start_lsl_threads("acquisition", collection_id)

                send_stdout()
                devs = list(streams.keys())
                fprint("UPDATOR:-Connect-")
                send_stdout()

            elif "dev_param_update" in data:
                None

            elif "record_start" in data:  #-> "record_start:FILENAME" FILENAME = {subj_id}_{task}
                fprint("Starting recording")
                fname = config.paths['data_out'] + data.split(":")[-1]
                for k in streams.keys():
                    if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
                        streams[k].start(fname)
                msg = "ACQ_ready"
                c.send(msg.encode("ascii"))
                fprint("ready to record")
                send_stdout()

            elif "record_stop" in data:
                fprint("Closing recording")
                for k in streams.keys():
                    if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
                        streams[k].stop()
                send_stdout()

            elif data in ["close", "shutdown"]:
                fprint("Closing devices")
                streams = close_streams(streams)
                send_stdout()

                if "shutdown" in data:
                    if lowFeed_running:
                        lowFeed.close()
                        lowFeed_running = False
                    fprint("Closing RTD cam")
                    break

            elif "time_test" in data:
                msg = f"ping_{time()}"
                c.send(msg.encode("ascii"))

            else:
                fprint("ACQ " + data)

    sleep(.5)
    s1.close()


Main()

