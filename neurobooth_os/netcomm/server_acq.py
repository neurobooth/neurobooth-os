import socket 
from time import time  
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import start_lsl_threads
import neurobooth_os.config
 
  
def Main(): 
    host = "" 
    time_del = 0
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
            lowFeed = VidRec_Brio(camindex=0, doPreview=True)    
            print ("Running low feed video streaming")
            
        elif "prepare" in data:
            streams = start_lsl_threads("acquisition")
            streams['micro'].start()
            print("Preparing devices")
            # TODO logger with devices initiated
        
        elif "record_start" in data:  #-> "record:FILENAME"
            fname = config.paths['data_out'] + data.split(":")[-1]            
            streams["hiFeed"].prepare(fname+".avi") 
            streams["intel"].prepare(fname )
            streams["hiFeed"].start()
            streams["intel"].start()
            c.send('recording'.encode("ascii"))
            print("Starting recording")
            
        elif "record_stop" in data: 
            streams["hiFeed"].stop()
            streams["intel"].stop()
            print("Closing recording")
            
        elif data in ["close", "shutdown"]: 
            if 'streams' in globals():
                for k in streams.key():
                    streams.stop()
            
            if 'lowFeed' in globals():
                lowFeed.close()
            
            print("Closing devices")
            
            if "shutdown" in data:    
                print("Closing Acq server")
                break
                
        elif "time_test" in data:
            msg = f"ping_{time()}"
            c.send(msg.encode("ascii"))
            

    s.close() 
  
  
Main() 
