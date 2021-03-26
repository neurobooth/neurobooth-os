import socket 
from time import time  
from iout.camera_brio import VidRec_Brio
from iout.lsl_streamer import start_lsl_threads

 
  
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
        
        elif "record" in data:  #-> "record:FILENAME"
            fname = data.split(":")[-1]
            streams["hiFeed"].prepare(fname) 
            streams["hiFeed"].record()
            print("Starting recording")
            
        elif "stop" in data: 
            streams["hiFeed"].stop()
            print("Closing recording")
            
        elif data in ["close", "shutdown"]: 
            streams["hiFeed"].close()
            lowFeed.close()
            streams['micro'].stop()
            print("Closing devices")
            
            if "shutdown" in data:    
                print("Closing Acq server")
                break
                
        elif "time_test" in data:
            c.send("ping_{time()}")
            
        
        # if "start_preparation" in data:
        #     time_del = time() - c_time
        #     c.send(f"Preparation started, t delay is {time_del}".encode('ascii')) 
        #     print(f"Preparation started, t delay is {time_del}") 
        #     # run_cam1()
        #     print ("Cameras running")

        # if "start_recording" in data:
        #     c.send("Starting recording".encode('ascii'))  
        #     print("Starting recording")

        # if "stop_recording" in data:
        #     c.send("Ending recording".encode('ascii'))  
        #     print("Ending recording")

    s.close() 
  
  
Main() 