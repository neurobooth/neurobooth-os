import socket, os
import io
import sys
from time import time, sleep
from iout.camera_brio import VidRec_Brio
from iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient
import config
import shutil
from netcomm.client import socket_message, node_info

os.chdir(r'C:\neurobooth-eel\\')

def Main(): 
    host = "" 
    lowFeed_running = False
    # reverse a port on your computer 
    # in our case it is 12345 but it 
    # can be anything 
    port = 12347
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port)) 
    print("socket binded to port", port) 
  
    # put the socket into listening mode 
    s.listen(5) 
    print("socket is listening") 
    
    # Capture prints for sending to serv ctr
    old_stdout = sys.stdout
    sys.stdout = mystdout = io.StringIO()
        
    def send_stdout():
        try:
            msg = mystdout.getvalue()         
            socket_message("ACQ: " + msg, "control")
            mystdout.truncate(0)
            mystdout.seek(0)
        except Exception as e: 
             print(e)
            
    def fprint(str_print):
        print(str_print)
        send_stdout()
        
    streams = {}
    # a forever loop until client wants to exit 
    while True: 
  
        # establish connection with client 
        try:
            c, addr = s.accept() 
            data = c.recv(1024)
        except: 
            continue
            
        if not data: 
            sys.stdout = old_stdout
            print("Connection fault, closing Stim server")
            break

        data = data.decode("utf-8")
                    
        # c_time = float(data.split("_")[-1][:-1])
        # print(f"time diff = {time() - c_time - time_del}")

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
            if len(streams):
                fprint("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("acquisition")            
                streams['micro'].start()
                if streams.get("mbient") is not None:
                   streams["mbient"].start()
            devs = list(streams.keys())
            fprint(f"ACQ devices prepared: {devs}")
            send_stdout()
            
    
        elif "record_start" in data:  #-> "record:FILENAME"
            fprint("Starting recording")            
            fname = config.paths['data_out'] + data.split(":")[-1]
            for k in streams.keys():
                if k[:-1] in ["hiFeed", "intel"]:
                    streams[k].start(fname)
            msg = "ACQ_ready"
            c.send(msg.encode("ascii"))
            fprint("ready to record")
            send_stdout()
            
        elif "record_stop" in data: 
            fprint("Closing recording")    
            for k in streams.keys():
                if k[:-1] in ["hiFeed", "intel"]:
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
            
        elif "connect_mbient" in data:
            mbient = connect_mbient()            
        else:
            fprint("ACQ" + data)
            
    sleep(.5)
    try:
        s.shutdown(socket.SHUT_RDWR)
    except:
            print("EXCEPTION: socket error shut down")
    try:
        s.close() 
    except:
            print("EXCEPTION: socket error close")
  
Main() 
shutil.copytree(config.paths["data_out"], config.paths['nas'], dirs_exist_ok=True)
