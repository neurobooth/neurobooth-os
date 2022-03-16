# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import sys
import time
import threading
from optparse import OptionParser
from datetime import datetime

import PySimpleGUI as sg
import liesl

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets, stream_plotter
from neurobooth_os.netcomm import get_messages_to_ctr, node_info, NewStdout, socket_message
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
    serv_data = serv_data.split(":::")[-1]
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
            # Initiating task:task_id:obs_id:tech_obs_log_id:tsk_strt_time
            _, task_id, obs_id, obs_log_id, tsk_strt_time = data_row.split(":")
            window.write_event_value('task_initiated', f"['{task_id}', '{obs_id}', '{obs_log_id}', '{tsk_strt_time}']")

        elif "Finished task:" in data_row:
            # Finished task: task_id
            _, task_id = data_row.split(":")
            window.write_event_value('task_finished', task_id)

        elif "-new_filename-" in data_row:
            # new file created, data_row = "-new_filename-:stream_name:video_filename"
            event, stream_name, filename = data_row.split(":")
            window.write_event_value(event, f"{stream_name},{filename}")
            

########## Database functions ############

def _find_subject(window, conn, first_name, last_name):
    """Find subject from database"""
    subject_df = meta.get_subject_ids(conn, first_name, last_name)
    window['dob'].update(values=subject_df['date_of_birth'])
    return subject_df


def _select_subject(window, subject_df):
    """Select subject from the DOB window"""
    subject = subject_df.iloc[window['dob'].get_indexes()]
    subject_id = subject.name
    first_name = subject['first_name_birth']
    last_name = subject['last_name_birth']

    # Update GUI
    window['dob'].update(values=[f'Subject ID: {subject_id}'])
    window['first_name'].update(disabled=True)
    window['last_name'].update(disabled=True)
    return first_name, last_name, subject_id


def _get_tasks(window, conn, collection_id):
    tasks_obs = meta.get_tasks(collection_id, conn)
    tasks = list()
    for task in tasks_obs:
        task_id, *_ = meta._get_task_param(task, conn)
        tasks.append(task_id)
    tasks = ", ".join(tasks)
    window["tasks"].update(value=tasks)
    return tasks


def _get_collections(window, conn, study_id):
    collection_ids = meta.get_collection_ids(study_id, conn)
    window["collection_id"].update(values=collection_ids)
    return collection_ids

def _save_session(window, tech_obs_log, staff_id, subject_id, first_name,
                  last_name, tasks):
    """Save session."""
    tech_obs_log["staff_id"] = staff_id
    tech_obs_log["subject_id"] = subject_id
    tech_obs_log["subject_id-date"] = f'{subject_id}_{datetime.now().strftime("%Y-%m-%d")}'

    subject_id_date = tech_obs_log["subject_id-date"]

    window.close()

    return {'subject_id': subject_id, 'first_name': first_name,
            'last_name': last_name, 'tasks': tasks, 'staff_id': staff_id,
            'subject_id_date': subject_id_date}


########## Task-related functions ############

def _start_task_presentation(window, tasks, subject_id, steps, node):
    """Present tasks"""
    window['Start'].Update(button_color=('black', 'yellow'))
    if len(tasks) > 0:
        running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
        socket_message(f"present:{running_task}:{subject_id}", node)
        steps.append("task_started")
    else:
        sg.PopupError('No task selected')


def _pause_tasks(steps, presentation_node):
    if "task_started" not in steps:
        sg.PopupError('Tasks not started')
    else:
        socket_message("pause tasks", presentation_node)
        resp = sg.Popup("The next task will be paused. \nDon't respond until end current task",
                        custom_text=('Continue or Stop tasks', "Calibrate"))
        if resp == 'Continue or Stop tasks':
            resp = sg.Popup( custom_text=('Continue tasks', 'Stop tasks',))
        socket_message(resp.lower(), presentation_node)


########## LSL functions ############

def _start_lsl_session(window, inlets, folder=''):
    window.write_event_value('start_lsl_session', 'none')

    # Create LSL session
    streamargs = [{'name': n} for n in list(inlets)]
    session = liesl.Session(prefix=folder, streamargs=streamargs,
                            mainfolder=cfg.paths["data_out"] )
    print("LSL session with: ", list(inlets))
    return session


def _record_lsl(window, session, subject_id, task_id, t_obs_id, obs_log_id,
                tsk_strt_time):

    print(f"task initiated: task_id {task_id}, t_obs_id {t_obs_id}, obs_log_id :{obs_log_id}")

    # Start LSL recording
    rec_fname = f"{subject_id}_{tsk_strt_time}_{t_obs_id}"
    session.start_recording(rec_fname)

    window["task_title"].update("Running Task:")
    window["task_running"].update(task_id, background_color="red")
    window['Start'].Update(button_color=('black', 'red'))
    return rec_fname


def _create_lsl_inlet(stream_ids, outlet_values, inlets):
    # event values -> f"['{outlet_name}', '{outlet_id}']
    outlet_name, outlet_id = eval(outlet_values)
    
    # update the inlet if new or different source_id
    if stream_ids.get(outlet_name) is None or outlet_id != stream_ids[outlet_name]:
        stream_ids[outlet_name] = outlet_id
        inlets.update(create_lsl_inlets({outlet_name: outlet_id}))


def _stop_lsl_and_save(window, session, conn, rec_fname, task_id, obs_log_id,
                       t_obs_id, folder):
    """Stop LSL stream and save"""

    # Stop LSL recording
    session.stop_recording()

    window["task_running"].update(task_id, background_color="green")
    window['Start'].Update(button_color=('black', 'green'))

    xdf_fname = get_xdf_name(session, rec_fname)
    split_sens_files(xdf_fname, obs_log_id, t_obs_id, conn, folder)

######### Server communication ############

def _start_servers(window, conn, nodes, remote=True):
    window['-init_servs-'].Update(button_color=('black', 'red'))
    event, values = window.read(.1)
    ctr_rec.start_servers(nodes=nodes, remote=remote, conn=conn)
    time.sleep(1)
    return event, values

def _start_ctr_server(window, host_ctr, port_ctr, remote=True):
    """Start threaded control server and new window."""

    # Start a threaded socket CTR server once main window generated
    callback_args = window
    server_thread = threading.Thread(target=get_messages_to_ctr,
                                    args=(_process_received_data, remote,
                                          host_ctr, port_ctr, callback_args,),
                                    daemon=True)
    server_thread.start()

    # Rerout print for ctr server to capture data in remote case
    if remote:
        time.sleep(.1)
        sys.stdout = NewStdout("mock",  target_node="dummy_ctr", terminal_print=True)


######### Visualization ############

def _plot_realtime(window, plttr, inlets):
    # if no inlets send event to prepare devices and make popup error
    if len(inlets) == 0:
        window.write_event_value('-Connect-')
        sg.PopupError('No inlet devices detected, preparing. Press plot once prepared')

    if plttr.pltotting_ts is True:
        plttr.inlets = inlets
    else:
        plttr.start(inlets)


def _update_button_status(window, statecolors, button_name, inlets, folder_session):
    if button_name in list(statecolors):
        # 2 colors for init_servers and Connect, 1 connected, 2 connected
        if len(statecolors[button_name]):
            color = statecolors[button_name].pop()
            window[button_name].Update(button_color=('black', color))

            # Signal start LSL session if both servers devices are ready:
            if button_name == "-Connect-" and color == "green":
                return _start_lsl_session(window, inlets, folder_session) 


def _prepare_devices(window, nodes, collection_id, tech_obs_log):
    """Prepare devices"""
    window['-Connect-'].Update(button_color=('black', 'red'))
    event, values = window.read(.1)

    vidf_mrkr = marker_stream('videofiles')
    # Create event to capture outlet_id
    window.write_event_value('-OUTLETID-', f"['{vidf_mrkr.name}', '{vidf_mrkr.oulet_id}']")

    nodes = ctr_rec._get_nodes(nodes)
    for node in nodes:
        socket_message(f"prepare:{collection_id}:{str(tech_obs_log)}", node)

    print('Connecting devices')
    return vidf_mrkr, event, values


def _get_ports(remote, database='neurobooth'):
    if remote:
        database = "mock_neurobooth"
        nodes = ('dummy_acq', 'dummy_stm')
        host_ctr, port_ctr = node_info("dummy_ctr")
    else:
        nodes = ('acquisition', 'presentation')
        host_ctr, port_ctr = node_info("control")
    return database, nodes, host_ctr, port_ctr


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
    database, nodes, host_ctr, port_ctr = _get_ports(remote, database='neurobooth')

    conn = meta.get_conn(remote=remote, database=database)
    window = _win_gen(_init_layout, conn)

    plttr = stream_plotter()
    tech_obs_log = meta._new_tech_log_dict()
    stream_ids, inlets = {}, {}
    plot_elem, inlet_keys = [], []

    statecolors = {"-init_servs-": ["green", "yellow"],
                   "-Connect-": ["green", "yellow"],
                   }
    steps = list()  # keep track of steps done
    event, values = window.read(.1)
    while True:
        event, values = window.read(.5)
        
        ############################################################
        # Initial Window -> Select subject, study and tasks 
        ############################################################
        if event == "study_id":
            study_id = values[event]
            tech_obs_log["study_id"] = study_id
            collection_ids = _get_collections(window, conn, study_id)

        elif event == 'find_subject':
            subject_df = _find_subject(window, conn, values['first_name'],
                                       values['last_name'])

        elif event == 'select_subject':
            first_name, last_name, subject_id = _select_subject(window, subject_df)

        elif event == "collection_id":
            collection_id = values[event]
            tech_obs_log["collection_id"] = collection_id
            tasks = _get_tasks(window, conn, collection_id)

        elif event == "_init_sess_save_":
            if values["tasks"] == "":
                sg.PopupError('No task combo')
            else:
                sess_info = _save_session(window,
                                          tech_obs_log, values['staff_id'],
                                          subject_id, first_name, last_name, tasks)
                # Open new layout with main window
                window = _win_gen(_main_layout, sess_info, remote)
                _start_ctr_server(window, host_ctr, port_ctr, remote=remote)

        ############################################################
        # Main Window -> Run neurobooth session
        ############################################################

        # Start servers on STM, ACQ
        elif event == "-init_servs-":
            _start_servers(window, conn, nodes, remote=remote)

        # Turn on devices
        elif event == '-Connect-':
            vidf_mrkr, event, values = _prepare_devices(window, nodes, collection_id,
                                                        tech_obs_log)

        elif event == 'plot':
            _plot_realtime(window, plttr, inlets)

        elif event == 'Start':
            tasks = [k for k, v in values.items() if "task" in k and v is True]
            _start_task_presentation(window, tasks, sess_info['subject_id'], steps,
                                     node=nodes[1])

        elif event == "Pause tasks":
            _pause_tasks(steps, presentation_node=nodes[1])

        # Save notes to a txt
        elif event == "_save_notes_":
            if values["_notes_taskname_"] == '':
                sg.PopupError('Pressed saving notes without task, select one in the dropdown list')
                continue

            write_task_notes(sess_info['subject_id_date'],
                             sess_info['staff_id'],
                             values['_notes_taskname_'], values['notes'])
            window["notes"].Update('')

        # Shut down the other servers and stops plotting
        elif event == 'Shut Down' or event == sg.WINDOW_CLOSED:
            plttr.stop()
            ctr_rec.shut_all(nodes=nodes)
            break

        ##################################################################################
        # Thread events from process_received_data -> received messages from other servers
        ##################################################################################
            
        # Signal a task started: record LSL data and update gui
        elif event == 'task_initiated':
            # event values -> f"['{task_id}', '{t_obs_id}', '{tech_obs_log_id}, '{tsk_strt_time}']
            task_id, t_obs_id, obs_log_id, tsk_strt_time = eval(values[event])
            rec_fname = _record_lsl(window, session, sess_info['subject_id_date'], task_id,
                                    t_obs_id, obs_log_id, tsk_strt_time)

        # Signal a task ended: stop LSL recording and update gui
        elif event == 'task_finished':
            task_id = values['task_finished']
            
            _stop_lsl_and_save(window, session, conn,
                               rec_fname, task_id, obs_log_id, t_obs_id, sess_info['subject_id_date'])

        # Send a marker string with the name of the new video file created
        elif event == "-new_filename-":            
            vidf_mrkr.push_sample([values[event]])
            print(f"pushed videfilename mark {values[event]}")

        # Update colors for: -init_servs-, -Connect-, Start buttons
        elif event == "-update_butt-":
            session = _update_button_status(window, statecolors, values['-update_butt-'],
                                            inlets, sess_info['subject_id_date'])

        # Create LSL inlet stream
        elif event == "-OUTLETID-":
            _create_lsl_inlet(stream_ids, values[event], inlets)

    ##################################################################################
    # Conditionals handling inlets for plotting and recording
    ##################################################################################
    
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
