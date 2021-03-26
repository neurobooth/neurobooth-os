import socket 

from time import time  
from iout.screen_capture import ScreenMirror
from iout.lsl_streamer import start_lsl_threads

  
  
def Main(): 
    host = "" 
    # time_del = 0
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
            print("Connection fault, closing Stim server")
            break

        data = data.decode("utf-8")
        print(data)
        
        # c_time = float(data.split("_")[-1][:-1])
        # print(f"time diff = {time() - c_time - time_del}")


        if "scr_stream" in data:
            screen_feed = ScreenMirror()
            screen_feed.start()
            print ("Stim screen feed running")
            
            
        elif "prepare" in data:
            streams = start_lsl_threads("presentation")
            streams['mouse'].start()
            print("Preparing devices")
            # TODO logger with devices initiated
            
            
        elif "present" in data:   #-> "present:FILENAME"
            task = data.split(":")[1]        
            print("initiating {task}") 
                  
            
        elif data in ["close", "shutdown"]: 
            streams['mouse'].stop()
            print("Closing devices")
             
            if "shutdown" in data:    
                print("Closing Stim server")
                break
        
        
        elif "time_test" in data:
            c.send("ping_{time()}")                     

    s.close() 
  
  
Main() 