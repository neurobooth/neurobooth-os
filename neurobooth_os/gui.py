# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import time
import re
import sys
import threading
import queue
from collections import OrderedDict
from datetime import datetime

import numpy as np

import PySimpleGUI as sg

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import update_streams_fromID, get_lsl_images, stream_plotter
from neurobooth_os.netcomm import get_messages_to_ctr
from neurobooth_os.layouts import _main_layout, _win_gen, _init_layout
import neurobooth_os.iout.metadator as meta


def _get_tasks(values):    
    tasks = []
    for key, val in values.items():
        if "task" in key and val is True:
            tasks.append(key)
    return tasks


serv_event = queue.Queue(maxsize=100)
thr = threading.Thread(target=get_messages_to_ctr, args=(serv_event,), daemon=True)
thr.start()


REMOTE=False, 
DATABASE='neurobooth'

conn = meta.get_conn(remote=REMOTE, database=DATABASE)

window = _win_gen(_init_layout, conn)


plttr = stream_plotter()


def new_tech_log_dict(application_id="neurobooth_os"):
    tech_obs_log = OrderedDict()
    tech_obs_log["subject_id"] = ""
    tech_obs_log["study_id"] = ""
    tech_obs_log["tech_obs_id"] = ""
    tech_obs_log["staff_id"] = ""
    tech_obs_log["application_id"] = "neurobooth_os"
    tech_obs_log["site_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tech_obs_log["event_array"] = []  # marker_name:timestamp
    tech_obs_log["collection_id"] = ""
    # tech_obs_log["date_times"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return tech_obs_log


inlets, stream_ids = {}, {}
def serv_data_received():
    # process CTR server received data
    global stream_ids, inlets, window

    while True:  # while items in queue
        try:
            event_feedb = serv_event.get(False)

            stream_ids_old = stream_ids.copy()
            # remove server name
            serv_name = event_feedb.split(": ")[0]
            event_feedb = event_feedb.replace("STM: ", "").replace("ACQ: ", "")
            print(serv_name, ":::")
            print("event_row " , event_row)

            for event_row in event_feedb.split("\n"):

                if "-OUTLETID-" in event_row:
                    # -OUTLETID-:OutletName:uuid
                    id_inf = re.search(
                        "-OUTLETID-:([A-Za-z_0-9]*):([A-Za-z_0-9]*)", event_row)
                    id_name, id_uuid = id_inf.groups()
                    stream_ids[id_name] = id_uuid             
                    if stream_ids_old != stream_ids or (len(stream_ids) and len(inlets) == 0):
                        inlets = update_streams_fromID(stream_ids)

                elif "UPDATOR:" in event_row:
                    # UPDATOR:-chars-
                    rout = re.search("UPDATOR:-([A-Za-z_]*)-", event_row)
                    for expr in rout.groups():
                        window.write_event_value('-update_butt-', expr)

                elif "Initiating task:" in event_row:
                    # Initiating task:task_id:obs_id
                    task_inf = re.search(
                        "Initiating task: ([A-Za-z_0-9]*):([A-Za-z_0-9]*)", event_row)
                    task_id, obs_id = task_inf.groups()
                    window["task_title"].update("Running Task:")
                    window["task_running"].update(task_id, background_color="red")
                    window['Start'].Update(button_color=('black', 'red'))

                elif "Finished task:" in event_row:
                    # Finished task:task_id
                    task_inf = re.search("Finished task: ([A-Za-z_0-9]*)", event_row)
                    task_id = task_inf.groups()
                    window["task_running"].update(task_id, background_color="green")
                    window['Start'].Update(button_color=('black', 'green'))

        except queue.Empty:
            break


tech_obs_log = new_tech_log_dict()
plot_elem, inlet_keys = [], [],
statecolors = {"init_servs": ["green", "yellow"],
               "Connect": ["green", "yellow"],
               }

event, values = window.read(.1)
while True:
    event, values = window.read(.5)

    serv_data_received()
    
    if event == sg.WIN_CLOSED:
        break

    ############################################################
    # Initial Window
    ############################################################
    elif event == "study_id":
        study_id = values[event]
        tech_obs_log["study_id"] = study_id
        collection_ids = meta.get_collection_ids(study_id, conn)
        window["collection_id"].update(values=collection_ids)

    elif event == "collection_id":
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
            sess_info = values
            tech_obs_log["staff_id"] = sess_info['staff_id']
            tech_obs_log["subject_id"] = sess_info['subj_id']
            window.close()
            # Open new layout with main window
            window = _win_gen(_main_layout, sess_info)

    ############################################################
    # Main Window
    ############################################################
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

        ctr_rec.prepare_devices(f"{collection_id}:{str(tech_obs_log)}")
        ctr_rec.initiate_labRec()
        print('Connecting devices')
        serv_data_received()
        inlets = update_streams_fromID(stream_ids)

    elif event == 'plot':
        event = "None"
        if len(inlets) == 0:
            ctr_rec.prepare_devices(collection_id)
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
        tasks = _get_tasks(values)

        inlets = update_streams_fromID(stream_ids)
        time.sleep(.5)
        
        serv_data_received()
        window['Start'].Update(button_color=('black', 'yellow'))
        if len(tasks):
            start_tasks = True
            running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
            ctr_rec.task_presentation(running_task, sess_info['subj_id'])
        else:
            sg.PopupError('No task selected')

    elif event == 'Shut Down':
        for k in list(inlets.keys()):
            if k in inlets.keys():
                inlets[k].close_stream()
                inlets.pop(k, None)
        ctr_rec.shut_all()
        plttr.stop()
        break

    if any(k for k in inlets.keys() if k in ["Webcam", "Screen"]):
        plot_elem = get_lsl_images(inlets)
        for elem in plot_elem:
            window[elem[0]].update(data=elem[1])

    serv_data_received()

    # Display LSL inlets
    if inlet_keys != list(stream_ids):
        inlet_keys = list(stream_ids)
        inlet_keys_disp = "\n".join(inlet_keys)
        window['inlet_State'].update(inlet_keys_disp)


window.close()
# window['-OUTPUT-'].__del__()
serv_data_received()
print("Session terminated")
