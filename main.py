import eel
from collections import OrderedDict
from pylsl import StreamInfo, StreamOutlet
from  iout.marker import marker_stream
from iout.lsl_streamer import  start_lsl_threads, close_threads
import os
import socket
import time
import json
import psutil
import config



# Initiate LSL streams and get threads
streams =  start_lsl_threads()
outlet_marker = marker_stream()



session_information = {"subject_id":"", "condition":"", "gender":"", "age":"", 
                       "rc_initials":"", "tasks":OrderedDict({"sync_test":True,
                        "dst":True, "mt":"mouse_tracking.html", "ft":True })}

tasks_html_pages = {"sync_test":"synch_task.html", 
                    "dst":"DSC_simplified_oneProbe_2020.html", 
                    "mt":"mouse_tracking.html",
                    "ft":"task_motor_assess/motortask_instructions.html"}


      
def find_checked_tasks(tasks):
    selected_tasks = []
    for key, selected in tasks.items():
        if selected:
            selected_tasks.append(key)
    print(selected_tasks)
    return selected_tasks
            
    
@eel.expose
def get_session_info(sub_id, condition, gender, age, rc_initials, check_st, check_dst, check_mt, check_ft):
    global session_information
    print(type(check_st))
    session_information["subject_id"] = sub_id
    session_information["condition"] = condition
    session_information["gender"] = gender
    session_information["age"] = age
    session_information["rc_initials"] = rc_initials
    session_information["tasks"]["sync_test"] = check_st
    session_information["tasks"]["dst"] = check_dst
    session_information["tasks"]["mt"] = check_mt
    session_information["tasks"]["ft"] = check_ft
    print(session_information)


    for key, selected in session_information["tasks"].items():
        
        if selected:
            if key == "sync_test":
                eel.go_to_link(tasks_html_pages[key])
                break
                
            elif key == "dst":
                eel.go_to_link(tasks_html_pages[key])
                break
            
            elif key == "mt":
                eel.go_to_link(tasks_html_pages[key])
                break

            elif key == "ft":
                eel.go_to_link(tasks_html_pages[key])
                break


@eel.expose
def get_data_mt(data):
    subj_id = session_information["subject_id"]
    with open(os.path.join('data', subj_id + '_mt' + '.json'), 'w', encoding='utf-8') as f:
        json.dump(data[1:-1], f, ensure_ascii=False, indent=4)              

@eel.expose
def get_data_dsst(results, score, outcomes):
    print(results, score, outcomes)
    

@eel.expose
def send_session_info():
    return session_information

@eel.expose
def message_from_js(msg):
    print(msg)

@eel.expose
def next_task(current_task):
    selected_tasks = find_checked_tasks(session_information["tasks"])
    print(current_task)
    index = selected_tasks.index(current_task)
    print(index)
    print(selected_tasks)
    if not current_task==selected_tasks[-1]:
        print(tasks_html_pages[selected_tasks[index+1]])
        eel.go_to_link(tasks_html_pages[selected_tasks[index+1]])
    else:
        print('../index.html')
        eel.go_to_link('../index.html')
        

@eel.expose
def send_marker(message, number=""):
    """ message str format "{Action name}_{trialInfo}_{task name}" """
    lsl_recording(message)
    outlet_marker.push_sample([f"{message}_{number}_{time.time()}"])      


def lsl_recording(message):
    action = message.split("_")[0]
    task_name = message.split("_")[-1]
    subj_id = session_information["subject_id"]
    
    cmd = "filename {root:" + config.paths['data_out'] + "} {template:%p_%b.xdf} {participant:" + subj_id + "_} {task:" + task_name + "}\n"
    
    if action == "start":        
        s.sendall(cmd.encode('utf-8') )
        time.sleep(.01)
        
        for vid in streams['strm_vids']:
            vid.record(config.paths['data_out'], f"{subj_id}_{task_name}" )                
        s.sendall(b"start\n")
        print("starting lsl aquisition")
        # time.sleep(.01)
        
    elif  action == "end":   
        s.sendall(b"stop\n")
        
        for vid in streams['strm_vids']:
            vid.recording = False
            
        print("ending lsl aquisition")


def prepare_devices():
    
    
    
    

# Start LabRecorder
if not "LabRecorder.exe" in (p.name() for p in psutil.process_iter()):
    os.startfile(config.paths['LabRecorder'])

time.sleep(.05)
s = socket.create_connection(("localhost", 22345))
s.sendall(b"select all\n")

eel.init('www', ['.js', '.html', '.jpg'])


eel.start('synch_task.html', size= (3840, 2160), cmdline_args=['--start-fullscreen', '--kisok'], geometry={'size': (3840, 2160), 'position': (0, 0)})

# eel.start('index.html', size= (3840, 2160), cmdline_args=['--start-fullscreen', '--kisok'], geometry={'size': (3840, 2160), 'position': (0, 0)})





   