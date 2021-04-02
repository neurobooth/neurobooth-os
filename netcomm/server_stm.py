import socket 

from time import time, sleep  
from iout.screen_capture import ScreenMirror
from iout.lsl_streamer import start_lsl_threads
import config
from netcomm.client import socket_message

  
def fake_task(s, cmd, subj_id, task_name):
    sleep(1)
    input("Press a key to start the task")
    sleep(1)
    
    print("Starting the Task")
    s.sendall(cmd.encode('utf-8') )
    sleep(.01)
    socket_message(f"record_start:{subj_id}_{task_name}", "acquisition")
    
    print("Do what you were told to, properly")
    sleep(3)
    
    print("Fairly well done, task is finished")
    s.sendall(b"stop\n")
    socket_message("record_stop", "acquisition")
    sleep(1)
    print("All closed, bye now")
    sleep(1)
    
    
# def tasks_presentation(task_name):
    
  
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
                       
            
        elif "present" in data:   #-> "present:TASKNAME:subj_id"
            task = data.split(":")[1]  
            subj_id = data.split(":")[2] 
            
            # Connection to LabRecorder in ctr pc
            s2 = socket.create_connection(('192.168.1.13', 22345))
            print(f"initiating {task}") 
            
            cmd = "filename {root:" + config.paths['data_out'] + "} {template:%p_%b.xdf} {participant:" + subj_id + "_} {task:" + task + "}\n"
            
            if task == "fakest_task":
                fake_task(s2, cmd, subj_id, task)   
                msg = f"Done with {task}"
                c.send(msg.encode("ascii")) 
                
            else:
                print(f"Task not {task} implemented")
           
            
        elif data in ["close", "shutdown"]: 
            streams['mouse'].stop()
            print("Closing devices")
             
            if "shutdown" in data:    
                print("Closing Stim server")
                break
        
        
        elif "time_test" in data:
            msg = f"ping_{time()}"
            c.send(msg.encode("ascii"))                     

    s.close() 
  
  
Main() 
