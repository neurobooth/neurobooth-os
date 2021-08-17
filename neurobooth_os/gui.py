# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import PySimpleGUI as sg
import numpy as np
import cv2
import pylsl
import time
import re
import sys
import threading
import matplotlib
import queue
from collections import OrderedDict
from datetime import datetime

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import update_streams_fromID, get_lsl_images, stream_plotter
from neurobooth_os.netcomm.server_ctr import server_com
from neurobooth_os.netcomm.client import socket_message
from neurobooth_os.layouts import main_layout, win_gen, init_layout
import neurobooth_os.iout.metadator as meta

def get_session_info(values):
     session_info = values        
     tasks = get_tasks(values)
     return session_info, tasks
    
    
def get_tasks(values): 
    tasks= []
    try:  # a key 0 is entered by some reason
        del values[0]
    except:
        pass
    
    for key, val in values.items():
        if "task" in key and val is True:
            tasks.append(key)
    return tasks            

def task_to_obs(task, obs_list):
    #match task to obs assuming taskname_task_n, obsname_obs taskname == obsname_obs
    for obs in obs_list:
        if task.split("_")[0] in obs:
            obs_id = obs
            return obs_id
        
        
def get_outlet_ids(str_prt, dic_ids):
    # Get outlet ids from ctr server, string format = Srv:-OUTLETID-:name:uuid "
    if str_prt.split(":")[0] == "-OUTLETID-":
        try:
            dic_ids[str_prt.split(":")[1]] = str_prt.split(":")[2]
        except:
            print(f"Outlet id bad formatted: {str_prt}")
    return dic_ids
    
serv_event = queue.Queue(maxsize=10)
def feedback_com():
    global serv_event    
    def callback(inp):
        serv_event.put(inp)
               
    server_com(callback)

thr = threading.Thread(target=feedback_com, daemon=True)
thr.start()

window = win_gen(init_layout)      

plttr = stream_plotter()

inlets, stream_ids = {}, {}
plot_elem, done_tasks, inlet_keys = [], [], []
running_task, start_tasks, session_saved = None, False, False
dev_prepared = False


def serv_data_received():
    # CTR server received data    
    global stream_ids, inlets
    
    while True:  # while items in queue
        try:
            # print("serv_data_received")
            event_feedb = serv_event.get(False)
            
            stream_ids_old = stream_ids.copy()
            # remove server name
            serv_name = event_feedb.split(": ")[0]
            event_feedb = event_feedb.replace("STM: ", "").replace("ACQ: ", "")
            print(serv_name,":::")
            print(event_feedb)
            if "-OUTLETID-" in event_feedb:
                for prt in event_feedb.split("\n"):
                    stream_ids = get_outlet_ids(prt, stream_ids)
                if stream_ids_old != stream_ids or ( len(stream_ids) and len(inlets)==0 ):
                    inlets = update_streams_fromID(stream_ids)
                    
            if "UPDATOR:" in event_feedb:
                #UPDATOR:-chars-
                rout= re.search("UPDATOR:-([A-Za-z_]*)-", event_feedb)
                for expr in rout.groups():                    
                    window.write_event_value('-update_butt-', expr)
            if "Initiating task:" in event_feedb:
                task_inf = re.search("Initiating task: ([A-Za-z_1-9]*):([A-Za-z_1-9]*)", event_feedb)
                task_id, obs_id = task_inf.groups()
                window["task_title"].update("Running Task:")
                window["task_running"].update(task_id, background_color="green")
                window['Start'].Update(button_color=('black', 'green'))
                
            if "Finished task:"  in event_feedb:
                task_inf = re.search("Finished task: ([A-Za-z_1-9]*)", event_feedb)
                task_id = task_inf.groups()
                window["task_running"].update(task_id, background_color="red")
                window['Start'].Update(button_color=('black', 'red'))
                
        except queue.Empty:
            break


conn = meta.get_conn()
log_id = meta.make_new_tech_obs_id()
   
tech_obs_log = OrderedDict()
tech_obs_log["tech_obs_log_id"] = ""
tech_obs_log["subject_id"] = ""
tech_obs_log["study_id"] = ""
tech_obs_log["tech_obs_id"] = ""
tech_obs_log["staff_id"] = ""
tech_obs_log["application_id"] = "neurobooth_os"
tech_obs_log["site_date"] = datetime.now().strftime("%Y_%m_%d")
tech_obs_log["event_array"] =[]
tech_obs_log["collection_name"] = ""
tech_obs_log["sensor_file_ids"] = ""
tech_obs_log["date_times"] = datetime.now().strftime("%Y_%m_%d")


statecolors = {"init_servs" : ["green", "yellow"],
               "Connect" :  ["green", "yellow"],
               }

event, values = window.read(.1) 
while True:
    event, values = window.read(.5)
    serv_data_received()
    
    if event == sg.WIN_CLOSED:
        break
    
    elif event == "study_id":
        print(event, values)
        study_id = values[event]   
        tech_obs_log["study_id"] = study_id
        collection_ids = meta.get_collection_ids(study_id, conn)        
        window["collection_id"].update(values=collection_ids)
        
    elif event == "collection_id":
        print(event, values)
        collection_id = values[event]
        tech_obs_log["collection_id"] = collection_id
        tasks_obs = meta.get_tasks(collection_id, conn)
        task_list = []
        for task in tasks_obs:
            task_id, _, _ = meta.get_task_param(task, conn)
            task_list.append(task_id)        
        window["_tasks_"].update(value=", ".join(task_list))
                
    elif event == "_init_sess_save_":
        if values["_tasks_"] == "":
            sg.PopupError('No task combo')
        else:
            if values.get(0):  # Wierd key with 0
                del values[0]
            sess_info = values
            subj_id = sess_info['subj_id']
            staff_id = sess_info['staff_id']   
            tech_obs_log["staff_id"] = staff_id
            tech_obs_log["subj_id"] = subj_id
            window.close()
            # Open new layout with main window            
            window = win_gen(main_layout, sess_info)
            
    elif event == "-update_butt-":
        if values['-update_butt-'] in list(statecolors):
            # 2 colors for init_servers and Connect, 1 connected, 2 connected
            if len(statecolors[values['-update_butt-']]):
                color = statecolors[values['-update_butt-']].pop()
                window[values['-update_butt-']].Update(button_color=('black', color))
            continue
        window[values['-update_butt-']].Update(button_color=('black', 'green'))
        
    elif event == "init_servs":        
        window['init_servs'].Update(button_color=('black', 'red'))
        event, values = window.read(.1)
        ctr_rec.start_servers()
        _ = ctr_rec.test_lan_delay(50)
        
    elif event == 'RTD':
        ctr_rec.prepare_feedback()
        print('RTD')
        time.sleep(1)
        serv_data_received()
                
    elif event == 'Connect':
        window['Connect'].Update(button_color=('black', 'red'))
        event, values = window.read(.1)
                                 
        ctr_rec.prepare_devices(collection_id) 
        ctr_rec.initiate_labRec()
        print('Connecting devices')
        serv_data_received()
        inlets = update_streams_fromID(stream_ids)
        dev_prepared = True
        
    
    elif event == 'plot':
        event = "None"
        if len(inlets) == 0:
            ctr_rec.prepare_devices() 
            serv_data_received()
            inlets = update_streams_fromID(stream_ids)
                       
        if plttr.pltotting_ts is True:
            inlets = update_streams_fromID(stream_ids)
            plttr.inlets = inlets
        else:
            plttr.start(inlets)
        
    elif event == 'Test_network':
        _ = ctr_rec.test_lan_delay(50)
                  
    elif event == 'Start':        
        session_info, tasks = get_session_info(values)
        session_info['subj_id'] = sess_info['subj_id']
        session_info['staff_id'] = sess_info['staff_id']
        session_info['study_id'] = sess_info['study_id']
        print(values)
        
        inlets = update_streams_fromID(stream_ids)
        time.sleep(.5)
        serv_data_received()
        window['Start'].Update(button_color=('black', 'yellow'))
        if len(tasks):
            start_tasks= True            
            running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3                       
            ctr_rec.task_presentation(running_task, session_info['subj_id'])
        else:
            print("Start button pressed but no task selected")      
     
    elif event ==  'Shut Down':
        for k in list(inlets.keys()):
            if k in inlets.keys():
                inlets[k].close_stream()
                inlets.pop(k, None)        
        ctr_rec.shut_all()
        session_saved = False
        plttr.stop()
        break
    
    if any(k for k in inlets.keys() if k in ["Webcam", "Screen"]):
        plot_elem = get_lsl_images(inlets) 
        for el in plot_elem:
            window[el[0]].update(data=el[1])
    
    serv_data_received()
    
    # Get LSL inlets
    if inlet_keys != list(stream_ids):
        inlet_keys =  list(stream_ids)
        inlet_keys_disp = "\n".join(inlet_keys)
        window['inlet_State'].update(inlet_keys_disp)
    # for k in stream_ids.keys():
    #     if k not in inlet_keys:
    #         inlet_keys.append(k)
    #         for inlet in inlet_keys:
          
            
            

window.close()
window['-OUTPUT-'].__del__()
serv_data_received()
print("Session terminated")