import socket 
from time import time, sleep
from iout.camera_brio import VidRec_Brio
from iout.lsl_streamer import start_lsl_threads, close_streams
import config
 


def Main(): 
    host = "" 
    time_del = 0
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
    streams = {}
    # a forever loop until client wants to exit 
    while True: 
  
        # establish connection with client 
        c, addr = s.accept() 
        data = c.recv(1024)
        if not data: 
            break

        data = data.decode("utf-8")
        print(data)
        
        # c_time = float(data.split("_")[-1][:-1])
        # print(f"time diff = {time() - c_time - time_del}")

        if "vis_stream" in data:
            if not lowFeed_running:
                lowFeed = VidRec_Brio(camindex=3, doPreview=True)    
                print ("Running low feed video streaming")
                lowFeed_running = True
            else:
                print ("Already running low feed video streaming")
            
        elif "prepare" in data:
            if len(streams):
                print("Closing devices before re-preparing")
                streams = close_streams(streams)
            streams = start_lsl_threads("acquisition")
            streams['micro'].start()
            print("Preparing devices")
    
        elif "record_start" in data:  #-> "record:FILENAME"
            fname = config.paths['data_out'] + data.split(":")[-1]            
            streams["hiFeed"].prepare(fname +".avi") 
            streams["intel"].prepare(fname)
            
            streams["hiFeed"].start()
            streams["intel"].start()
            
            c.send('recording'.encode("ascii"))
            print("Starting recording")
            
        elif "record_stop" in data: 
            streams["hiFeed"].stop()
            streams["intel"].stop()
            print("Closing recording")
            
        elif data in ["close", "shutdown"]: 
            print("Closing devices")
            streams = close_streams(streams)
            
            if "shutdown" in data:    
                if lowFeed_running:
                    lowFeed.close()                
                print("Closing Acq server")
#                break
                
        elif "time_test" in data:
            msg = f"ping_{time()}"
            c.send(msg.encode("ascii"))
            
    sleep(.5)
    try:
        s.shutdown(socket.SHUT_RDWR)
    except:
            print("socket error shut down")
    
    try:
        s.close() 
    except:
            print("socket error close")
  
Main() 
