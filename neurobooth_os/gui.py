# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import time
import threading
from collections import OrderedDict
from datetime import datetime

import PySimpleGUI as sg

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import update_streams_fromID, get_lsl_images, stream_plotter
from neurobooth_os.netcomm import get_messages_to_ctr
from neurobooth_os.layouts import _main_layout, _win_gen, _init_layout
import neurobooth_os.iout.metadator as meta



REMOTE=False, 
DATABASE='neurobooth'

conn = meta.get_conn(remote=REMOTE, database=DATABASE)
window = _win_gen(_init_layout, conn)


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



def process_received_data(serv_data, window):
    """ Gets string data from other servers and create PySimpleGui window events.

    Parameters
    ----------
    serv_data : str
        Data sent by other servers
    window : object
        PySimpleGui window object
    """

    # Split server name and data
    serv_name, serv_data = serv_data.split(":::")
    print(serv_name, ":::")
    print("serv_data " , serv_data)

    for data_row in serv_data.split("\n"):
        if "-OUTLETID-" in data_row:
            # -OUTLETID-:outlet_name:uuid
            evnt, outlet_name, outlet_id = data_row.split(":")
            window.write_event_value('-OUTLETID-', f"['{outlet_name}', '{outlet_id}']")

        elif "UPDATOR:" in data_row:
            # UPDATOR:-elem_key-
            elem = data_row.split(":")[1]
            window.write_event_value('-update_butt-', elem)

        elif "Initiating task:" in data_row:
            # Initiating task:task_id:obs_id
            _, task_id, obs_id = data_row.split(":")
            window.write_event_value('task_initiated', f"['{task_id}', '{obs_id}']")

        elif "Finished task:" in data_row:
            # Finished task: task_id
            _, task_id = data_row.split(":")
            window.write_event_value('task_finished', task_id)


ctr_thr = threading.Thread(target=get_messages_to_ctr, args=(process_received_data, window,), daemon=True)
ctr_thr.start()



plttr = stream_plotter()
tech_obs_log = new_tech_log_dict()
stream_ids = {}
plot_elem, inlet_keys = [], [],
statecolors = {"init_servs": ["green", "yellow"],
               "Connect": ["green", "yellow"],
               }

event, values = window.read(.1)
while True:
    event, values = window.read(.5)
    
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

    elif event == 'RTD':  # TODO signal when RTD finishes
        ctr_rec.prepare_feedback()
        print('RTD')
        time.sleep(1)

    elif event == 'Connect':
        window['Connect'].Update(button_color=('black', 'red'))
        event, values = window.read(.1)

        ctr_rec.prepare_devices(f"{collection_id}:{str(tech_obs_log)}")
        ctr_rec.initiate_labRec()
        print('Connecting devices')

    elif event == "-OUTLETID-":
        # event values -> f"['{outlet_name}', '{outlet_id}']
        outlet_name, outlet_id = eval(values[event])

        # update inlet if new or outlet_id new != old   
        if stream_ids.get(outlet_name) is None or outlet_id != stream_ids[outlet_name]:
            stream_ids[outlet_name] = outlet_id
            inlets = update_streams_fromID(stream_ids)  # TODO update only new outid

    elif event == 'plot':
        # if no inlets sent event to prepare devices and make popup error
        if len(inlets) == 0:
            window.write_event_value('Connect')
            sg.PopupError('No inlet devices detected, preparing. Press plot once prepared')

        if plttr.pltotting_ts is True:
            plttr.inlets = inlets
        else:
            plttr.start(inlets)

    elif event == 'Test_network':
        _ = ctr_rec.test_lan_delay(50)

    elif event == 'Start':
        tasks = [k for k, v in values.items() if "task" in k and v == True]
                
        window['Start'].Update(button_color=('black', 'yellow'))
        if len(tasks):
            running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
            ctr_rec.task_presentation(running_task, sess_info['subj_id'])
        else:
            sg.PopupError('No task selected')

    elif event == 'task_initiated':
        # event values -> f"['{task_id}', '{obs_id}']
        task_id, obs_id = eval(values[event])

        window["task_title"].update("Running Task:")
        window["task_running"].update(task_id, background_color="red")
        window['Start'].Update(button_color=('black', 'red'))

    elif event == 'task_finished':
        task_id = values[event]
        window["task_running"].update(task_id, background_color="green")
        window['Start'].Update(button_color=('black', 'green'))

    elif event == 'Shut Down':
        plttr.stop()
        ctr_rec.shut_all()
        break

    # Plotting STM screen or webcam
    if any(k for k in inlets.keys() if k in ["Webcam", "Screen"]):
        plot_elem = get_lsl_images(inlets)
        for elem in plot_elem:
            window[elem[0]].update(data=elem[1])

    # Display LSL inlets
    if inlet_keys != list(stream_ids):
        inlet_keys = list(stream_ids)
        inlet_keys_disp = "\n".join(inlet_keys)
        window['inlet_State'].update(inlet_keys_disp)


window.close()
window['-OUTPUT-'].__del__()
print("Session terminated")
