# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import sys
import time
import threading
from optparse import OptionParser

import PySimpleGUI as sg
import liesl

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets, get_lsl_images, stream_plotter
from neurobooth_os.netcomm import get_messages_to_ctr, node_info, NewStdout
from neurobooth_os.layouts import _main_layout, _win_gen, _init_layout, write_task_notes
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.split_xdf import split_sens_files, get_xdf_name
from neurobooth_os.iout import marker_stream
import neurobooth_os.config as cfg

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
    # print(serv_name, ":::")
    for data_row in serv_data.split("\n"):
        # print("\t " , data_row)

        if "-OUTLETID-" in data_row:
            # -OUTLETID-:outlet_name:uuid
            # print("Signaling outletid")
            evnt, outlet_name, outlet_id = data_row.split(":")
            window.write_event_value('-OUTLETID-', f"['{outlet_name}', '{outlet_id}']")

        elif "UPDATOR:" in data_row:
            # UPDATOR:-elem_key-
            elem = data_row.split(":")[1]
            window.write_event_value('-update_butt-', elem)

        elif "Initiating task:" in data_row:
            # Initiating task:task_id:obs_id:tech_obs_log_id
            _, task_id, obs_id, obs_log_id = data_row.split(":")
            window.write_event_value('task_initiated', f"['{task_id}', '{obs_id}', '{obs_log_id}']")

        elif "Finished task:" in data_row:
            # Finished task: task_id
            _, task_id = data_row.split(":")
            window.write_event_value('task_finished', task_id)

        elif "-new_filename-" in data_row:
            # new file created, data_row = "-new_filename-:stream_name:video_filename"
            print(f"catched {data_row}")
            event, stream_name, filename = data_row.split(":")
            window.write_event_value(event, f"{stream_name}, {filename}]")
            

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
                task_id, *_ = meta._get_task_param(task, conn)
                task_list.append(task_id)
            window["_tasks_"].update(value=", ".join(task_list))

        elif event == "_init_sess_save_":
            if values["_tasks_"] == "":
                sg.PopupError('No task combo')
            else:
                sess_info = values
                subject_id, staff_id = sess_info['subj_id'], sess_info['staff_id']
                tech_obs_log["staff_id"] = sess_info['staff_id']
                tech_obs_log["subject_id"] = sess_info['subj_id']
                window.close()
                # Open new layout with main window
                window = _win_gen(_main_layout, sess_info, remote)

                # Start a threaded socket CTR server once main window generated
                callback_args = window    
                server_thread = threading.Thread(target=get_messages_to_ctr,
                                                args=(_process_received_data, host_ctr, port_ctr,
                                                callback_args,),
                                                daemon=True)
                server_thread.start()

                # Rerout print for ctr server to capture data in remote case
                if remote:
                    time.sleep(.1)
                    sys.stdout = NewStdout("mock",  target_node="dummy_ctr", terminal_print=True)

        ############################################################
        # Main Window -> Run neurobooth session
        ############################################################

        # Start servers on STM, ACQ
        elif event == "-init_servs-":
            window['-init_servs-'].Update(button_color=('black', 'red'))
            event, values = window.read(.1)
            ctr_rec.start_servers(nodes=nodes, remote=remote, conn=conn)
            time.sleep(1)
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

            ctr_rec.prepare_devices(f"{collection_id}:{str(tech_obs_log)}", nodes=nodes)
            vidf_mrkr = marker_stream('videofiles')
            # Create event to capture outlet_id
            window.write_event_value('-OUTLETID-', f"['{vidf_mrkr.name}', '{vidf_mrkr.outlet_id}']")

            print('Connecting devices')

        # Real-time plotting of inlet data.
        elif event == 'plot':
            # if no inlets send event to prepare devices and make popup error
            if len(inlets) == 0:
                window.write_event_value('-Connect-')
                sg.PopupError('No inlet devices detected, preparing. Press plot once prepared')

            if plttr.pltotting_ts is True:
                plttr.inlets = inlets
            else:
                plttr.start(inlets)

        # Start task presentation.
        elif event == 'Start':
            tasks = [k for k, v in values.items() if "task" in k and v == True]
                    
            window['Start'].Update(button_color=('black', 'yellow'))
            if len(tasks):
                running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
                ctr_rec.task_presentation(running_task, sess_info['subj_id'],
                                          node=nodes[1])
            else:
                sg.PopupError('No task selected')

        # Save notes to a txt
        elif event == "_save_notes_":
            if values["_notes_taskname_"] == '':
                sg.PopupError('Pressed saving notes without task, select one in the dropdown list')
                continue

            write_task_notes(subject_id, staff_id, values['_notes_taskname_'], values['notes'])
            window["notes"].Update('')

        # Shut down the other servers and stops plotting
        elif event == 'Shut Down' or event == sg.WINDOW_CLOSED:
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

                    #Signal start LSL session if both servers devices are ready:
                    if values['-update_butt-'] == "-Connect-" and color == "green":
                        window.write_event_value('start_lsl_session', 'none')
                continue
            window[values['-update_butt-']].Update(button_color=('black', 'green'))

        # Create LSL inlet stream
        elif event == "-OUTLETID-":
            # event values -> f"['{outlet_name}', '{outlet_id}']
            outlet_name, outlet_id = eval(values[event])
            
            # update the inlet if new or different source_id
            if stream_ids.get(outlet_name) is None or outlet_id != stream_ids[outlet_name]:
                stream_ids[outlet_name] = outlet_id
                new_inlet = create_lsl_inlets({outlet_name: outlet_id})
                inlets.update(new_inlet)

        # Signal a task started: record LSL data and update gui
        elif event == 'task_initiated':
            # event values -> f"['{task_id}', '{t_obs_id}', '{tech_obs_log_id}']
            task_id, t_obs_id, obs_log_id = eval(values[event])
            print(f"task initiated: task_id {task_id}, t_obs_id {t_obs_id}, obs_log_id :{obs_log_id}")
            # Start LSL recording
            rec_fname = f"{subject_id}-{t_obs_id}"
            session.start_recording(rec_fname)

            window["task_title"].update("Running Task:")
            window["task_running"].update(task_id, background_color="red")
            window['Start'].Update(button_color=('black', 'red'))

        # Signal a task ended: stop LSL recording and update gui
        elif event == 'task_finished':
            task_id = values[event]
            
            # Stop LSL recording
            session.stop_recording()

            window["task_running"].update(task_id, background_color="green")
            window['Start'].Update(button_color=('black', 'green'))

            xdf_fname = get_xdf_name(session, rec_fname)
            split_sens_files(xdf_fname, obs_log_id, t_obs_id, conn)

        # Send a marker string with the name of the new video file created
        elif event == "-new_filename-":            
            vidf_mrkr.push_sample([values[event]])
            print(f"pushed videfilename mark {values[event]}")

        ##################################################################################
        # Conditionals handling inlets for plotting and recording
        ##################################################################################

        # Create a lielsl session for recording data
        elif event == 'start_lsl_session':
            streamargs = [{'name': n} for n in list(inlets)]
            session = liesl.Session(prefix='',
                                        streamargs=streamargs, mainfolder=cfg.paths["data_out"] )
            print("LSL session with: ", list(inlets))

        # Plot STM screen or webcam frames
        if any(k for k in inlets.keys() if k in ["Webcam", "Screen"]):
            plot_elem = get_lsl_images(inlets)
            for elem in plot_elem:
                window[elem[0]].update(data=elem[1])

        # Print LSL inlet names in GUI
        if inlet_keys != list(inlets):
            inlet_keys = list(inlets)
            window['inlet_State'].update("\n".join(inlet_keys))

    window.close()
    if remote:
        sys.stdout = sys.stdout.terminal
    else:
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
