# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import time
import threading
from optparse import OptionParser

import PySimpleGUI as sg

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets, get_lsl_images, stream_plotter
from neurobooth_os.netcomm import get_messages_to_ctr, node_info
from neurobooth_os.layouts import _main_layout, _win_gen, _init_layout
import neurobooth_os.iout.metadator as meta


def _process_received_data(serv_data, window):
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


def gui(remote=False, database='neurobooth'):
    """Start the Graphical User Interface.

    Parameters
    ----------
    remote : bool
        If True, uses ssh_tunnel to connect and database = mock_neurobooth
        to the database. Use False if on site.
    database : str
        The database name
    """

    
    if remote:
        database = "mock_neurobooth"
        nodes = ('dummy_acq', 'dummy_stm')
        host_ctr, port_ctr = node_info("dummy_ctr")
    else:
        nodes = ('acquisition', 'presentation')
        host_ctr, port_ctr = node_info("control")


    conn = meta.get_conn(remote=remote, database=database)
    window = _win_gen(_init_layout, conn)

    plttr = stream_plotter()
    tech_obs_log = meta._new_tech_log_dict()
    stream_ids, inlets = {}, {}
    plot_elem, inlet_keys = [], [],
    statecolors = {"-init_servs-": ["green", "yellow"],
                   "-Connect-": ["green", "yellow"],
                   }

    event, values = window.read(.1)
    while True:
        event, values = window.read(.5)
        
        ############################################################
        # Initial Window -> Select subject, study and tasks 
        ############################################################
        if event == "study_id":
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
                window = _win_gen(_main_layout, sess_info, remote)

                # Start a threaded socket CTR server once main window gnerated
                callback_args = window    
                server_thread = threading.Thread(target=get_messages_to_ctr,
                                                args=(_process_received_data, host_ctr, port_ctr,
                                                callback_args,),
                                                daemon=True)
                server_thread.start()

        ############################################################
        # Main Window -> Run neurobooth session
        ############################################################

        # Start servers on STM, ACQ
        elif event == "-init_servs-":
            window['-init_servs-'].Update(button_color=('black', 'red'))
            event, values = window.read(.1)
            ctr_rec.start_servers(nodes=nodes, remote=remote, conn=conn)
            _ = ctr_rec.test_lan_delay(50, nodes=nodes)

        # Real time display (RTD)
        elif event == 'RTD':  # TODO signal when RTD finishes
            ctr_rec.prepare_feedback()
            print('RTD')
            time.sleep(1)

        # Turn on devices and start LSL outlet stream
        elif event == '-Connect-':
            window['-Connect-'].Update(button_color=('black', 'red'))
            event, values = window.read(.1)

            ctr_rec.prepare_devices(f"{collection_id}:{str(tech_obs_log)}",
                                    nodes=nodes)
            print('Connecting devices')

        # Real-time plotting of inlet data.
        elif event == 'plot':
            # if no inlets sent event to prepare devices and make popup error
            if len(inlets) == 0:
                window.write_event_value('-Connect-')
                sg.PopupError('No inlet devices detected, preparing. Press plot once prepared')

            if plttr.pltotting_ts is True:
                plttr.inlets = inlets
            else:
                plttr.start(inlets)

        # Start task presentation.
        elif event == 'Start':
            print(values)
            tasks = [k for k, v in values.items() if "task" in k and v == True]
                    
            window['Start'].Update(button_color=('black', 'yellow'))
            if len(tasks):
                running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
                ctr_rec.task_presentation(running_task, sess_info['subj_id'],
                                          node=nodes[1])
            else:
                sg.PopupError('No task selected')

        # Shut down the other servers and stops plotting
        elif event == 'Shut Down' or sg.WINDOW_CLOSED:
            plttr.stop()
            ctr_rec.shut_all(nodes=nodes)
            break

        ##################################################################################
        # Thread events from process_received_data -> received messages from other servers
        ##################################################################################

        # Update colors for: -init_servs-, -Connect-, Start buttons
        elif event == "-update_butt-":
            if values['-update_butt-'] in list(statecolors):
                # 2 colors for init_servers and Connect, 1 connected, 2 connected
                if len(statecolors[values['-update_butt-']]):
                    color = statecolors[values['-update_butt-']].pop()
                    window[values['-update_butt-']].Update(button_color=('black', color))
                continue
            window[values['-update_butt-']].Update(button_color=('black', 'green'))

        # Create LSL inlet stream
        elif event == "-OUTLETID-":
            # event values -> f"['{outlet_name}', '{outlet_id}']
            outlet_name, outlet_id = eval(values[event])

            # update inlet if new or outlet_id new != old   
            if stream_ids.get(outlet_name) is None or outlet_id != stream_ids[outlet_name]:
                stream_ids[outlet_name] = outlet_id
                inlets = create_lsl_inlets(stream_ids)  # TODO update only new outid

        # Signal a task started: record LSL data and update gui
        elif event == 'task_initiated':
            # event values -> f"['{task_id}', '{obs_id}']
            task_id, obs_id = eval(values[event])

            window["task_title"].update("Running Task:")
            window["task_running"].update(task_id, background_color="red")
            window['Start'].Update(button_color=('black', 'red'))

        # Signal a task ended: stop LSL recording and update gui
        elif event == 'task_finished':
            task_id = values[event]
            window["task_running"].update(task_id, background_color="green")
            window['Start'].Update(button_color=('black', 'green'))

        # Plot STM screen or webcam frames
        if any(k for k in inlets.keys() if k in ["Webcam", "Screen"]):
            plot_elem = get_lsl_images(inlets)
            for elem in plot_elem:
                window[elem[0]].update(data=elem[1])

        # Print LSL inlet names in GUI
        if inlet_keys != list(stream_ids):
            inlet_keys = list(stream_ids)
            inlet_keys_disp = "\n".join(inlet_keys)
            window['inlet_State'].update(inlet_keys_disp)


    window.close()
    if not remote:
        window['-OUTPUT-'].__del__()
    print("Session terminated")


def main():
    """The starting point of Neurobooth"""
    parser = OptionParser()
    parser.add_option("-r", "--remote", dest="remote", action="store_true",
                      default=False, help="Access database using remote connection")
    (options, args) = parser.parse_args()
    gui(remote=options.remote)

if __name__ == '__main__':
    main()
