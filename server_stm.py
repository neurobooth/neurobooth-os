import socket 
import io
import pandas as pd
import sys
import os
from time import time, sleep  
from iout.screen_capture import ScreenMirror
from iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient

import config
from netcomm.client import socket_message, node_info

from tasks.test_timing.audio_video_test import Timing_Test
from tasks.wellcome_finish_screens import welcome_screen, finish_screen
import tasks.utils as utl
from tasks.task_importer import get_task_funcs

os.chdir(r'C:\neurobooth-eel\\')
print(os.getcwd())

def fake_task(**kwarg):
    sleep(10)
    


def run_task(task_funct, s2, cmd, subj_id, task, send_stdout, task_karg={}):    
    resp = socket_message(f"record_start:{subj_id}_{task}", "acquisition", wait_data=2)
    print(resp)
    s2.sendall(cmd.encode('utf-8') )
    sleep(.5)
    s2.sendall(b"select all\n")
    sleep(.5)
    s2.sendall(b"start\n")
    sleep(.5)
    res = task_funct(**task_karg)
    s2.sendall(b"stop\n")
    socket_message("record_stop", "acquisition")
    sleep(2)
    return res
                
              
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
    
    # Capture prints for sending to serv ctr
    old_stdout = sys.stdout
    sys.stdout = mystdout = io.StringIO()
        
    def send_stdout():
        try:
            msg = mystdout.getvalue()         
            socket_message("STM: " + msg, "control")
            mystdout.truncate(0)
            mystdout.seek(0)
        except Exception as e: 
            print(e)

    def fprint(str_print):
        print(str_print)
        send_stdout()

    win = utl.make_win(full_screen=False)
    
    # Signal event to change init_serv button to green
    fprint ("UPDATOR:-init_servs-")
    
    # win = welcome_screen(with_audio=True)
    streams, screen_running = {}, False            
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
            
        # send_stdout()
        # c_time = float(data.split("_")[-1][:-1])
        # print(f"time diff = {time() - c_time - time_del}")


        if "scr_stream" in data:
            if not screen_running:
                screen_feed = ScreenMirror()
                screen_feed.start()
                fprint ("Stim screen feed running")
                screen_running = True
            else:
                fprint(f"-OUTLETID-:Screen:{screen_feed.oulet_id}")
                fprint ("Already running screen feed")
            send_stdout()
            
        elif "prepare" in data:
            # data = "prepare:collection_id"
            
            collection_id = data.split(":")[-1]
            task_func_dict = get_task_funcs(collection_id)
            
            if len(streams):
                fprint("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:    
                streams = start_lsl_threads("presentation", collection_id, win=win)
                send_stdout()
                streams['mouse'].start()
                if 'eye_tracker' in streams.keys():
                    streams['eye_tracker'].win = win
                fprint("Preparing devices")
                            
        elif "present" in data:   #-> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3  
            tasks = data.split(":")[1].split("-")
            tasks = ["pursuit_task_1", "DSC_task_1", "mouse_task_1", "sit_to_stand_task_1"]
            tasks = ["DSC_task_1", "mouse_task_1", "sit_to_stand_task_1"]

            subj_id = data.split(":")[2] 
            
            win = welcome_screen(with_audio=True, win=win)

            # Connection to LabRecorder in ctr pc
            host_ctr, _ = node_info("control")
            s2 = socket.create_connection((host_ctr, 22345))
            
            for task in tasks:                
                host_ctr, _ = node_info("control")
                fprint(f"initiating {task}") 
                send_stdout()
                
                cmd = "filename {root:" + config.paths['data_out'] + "} {template:%p_%b.xdf} {participant:" + subj_id + "_} {task:" + task + "}\n"
                
                task_karg ={"win": win,
                            "path": config.paths['data_out'],
                            "subj_id": subj_id,
                            "eye_tracker": streams['eye_tracker'],
                            "marker_outlet": streams['marker'],
                            "event_marker": streams['marker']}
                
                if task in task_func_dict.keys():
                    tsk_fun = task_func_dict[task] 
                    # c.send(msg.encode("ascii")) 
                    fprint(f"Starting task: {task}") 
                    res = run_task(tsk_fun, s2, cmd, subj_id, task, send_stdout, task_karg)
                        
                    streams['eye_tracker'].stop()
                    fprint(f"Finished task: {task}") 
                    
                elif task == 'timing_task':
                    fprint(f"Starting {task}") 
                    run_task(Timing_Test, s2, cmd, subj_id, task, send_stdout, task_karg)
                    fprint(f"Finished task: {task}") 

                else:
                    fprint(f"Task not {task} implemented")
                
            finish_screen(win)
            
        elif data in ["close", "shutdown"]: 
            
            streams = close_streams(streams)          
            fprint("Closing devices")
            send_stdout()
             
            if "shutdown" in data:    
                if screen_running:
                    screen_feed.stop()
                    fprint("Closing screen mirroring")                    
                    screen_running = False
                fprint("Closing Stim server")          
                break
        
        elif "time_test" in data:
            msg = f"ping_{time()}"
            c.send(msg.encode("ascii"))
        elif "connect_mbient" in data:
            
            mbient = connect_mbient()

        else: 
            fprint(data)
                             
    
    s.close() 
    sys.stdout = old_stdout
    win.close()
  
  
Main() 
