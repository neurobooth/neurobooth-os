
import threading
import sys 
import PySimpleGUI as sg
import liesl
from time import sleep as tsleep

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.netcomm import get_messages_to_ctr, node_info, NewStdout
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout import marker_stream
from neurobooth_os.gui import _process_received_data
from neurobooth_os.mock import mock_server_stm, mock_server_acq
from neurobooth_os.layouts import _main_layout, _win_gen
from neurobooth_os.realtime.lsl_plotter import create_lsl_inlets
from neurobooth_os.iout.split_xdf import split_sens_files, get_xdf_name
import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg


def wind_gen(window, nodes, timeout=1):
    while True:
        event, values = window.read(timeout)
        if event == '__TIMEOUT__':
            break
        elif event == 'Shut Down' or event == sg.WINDOW_CLOSED:
            ctr_rec.shut_all(nodes=nodes)
        yield event, values


def threaded_signals(window, event, values, subject_id, statecolors=None, stream_ids=None,
                     inlets=None, out={}):
    
    # Update colors for: -init_servs-, -Connect-, Start buttons
    if event == "-update_butt-":
        if values['-update_butt-'] in list(statecolors):
            # 2 colors for init_servers and Connect, 1 connected, 2 connected
            if len(statecolors[values['-update_butt-']]):
                color = statecolors[values['-update_butt-']].pop()
                window[values['-update_butt-']].Update(button_color=('black', color))

                #Signal start LSL session if both servers devices are ready:
                if values['-update_butt-'] == "-Connect-" and color == "green":
                    window.write_event_value('start_lsl_session', 'none')
                    threaded_signals(event, values, statecolors)

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
        out["obs_log_id"] = obs_log_id
        out["t_obs_id"] = t_obs_id
        out["task_id"] = task_id
        print(f"task initiated: task_id {task_id}, t_obs_id {t_obs_id}, obs_log_id :{obs_log_id}")
        # Start LSL recording
        out["rec_fname"] = f"{subject_id}-{t_obs_id}"
        out['session'].start_recording(out["rec_fname"])

        window["task_title"].update("Running Task:")
        window["task_running"].update(task_id, background_color="red")
        window['Start'].Update(button_color=('black', 'red'))

    # Signal a task ended: stop LSL recording and update gui
    elif event == 'task_finished':
        task_id = values[event]
        
        # Stop LSL recording
        out['session'].stop_recording()

        window["task_running"].update(task_id, background_color="green")
        window['Start'].Update(button_color=('black', 'green'))

        xdf_fname = get_xdf_name(out['session'], out["rec_fname"])
        split_sens_files(xdf_fname, out["obs_log_id"], out["t_obs_id"], conn)

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
        out['session'] = liesl.Session(prefix='',
                                    streamargs=streamargs, mainfolder=cfg.paths["data_out"] )
        print("LSL session with: ", list(inlets))

    out['values'] = values
    return out


# Define parameters
sess_info = {"subj_id":"test_nogui", "staff_id":"AN", '_tasks_': "mock_task_1"}
collection_id = "mock_collection"  # Define mock with tasks to run
nodes = ('dummy_acq', 'dummy_stm')

tech_obs_log = meta._new_tech_log_dict()
tech_obs_log["study_id"] = 'mock_study'
tech_obs_log["collection_id"] = collection_id
tech_obs_log["staff_id"] = sess_info['staff_id']
tech_obs_log["subject_id"] = sess_info['subj_id']
subj_id = sess_info['subj_id']

# Get DB connexion
remote = True
conn = meta.get_conn(remote=remote)

# Create mock CTR
window = _win_gen(_main_layout, sess_info, remote)
event, values = window.read(.1)
ctr_host, ctr_port = node_info("dummy_ctr")   
callback, callback_args = _process_received_data, window    
server_thread = threading.Thread(target=get_messages_to_ctr,
                                    args=(callback, ctr_host, ctr_port, callback_args,),
                                    daemon=True)
server_thread.start()
tsleep(.3)

# Rerout stdout to dummy_ctr and print in terminal
sys.stdout = NewStdout("mock",  target_node="dummy_ctr", terminal_print=True)

# Create mockACQ and STM servers
mk_acq_thr = mock_server_acq(conn)
mk_stm_thr = mock_server_stm(conn)
tsleep(.3)

# automatically run session
out, stream_ids, inlets,  = {}, {}, {}
statecolors = {"-init_servs-": ["green", "yellow"],
                "-Connect-": ["green", "yellow"],
               }

# Prepare device
vidf_mrkr = marker_stream('videofiles')
window.write_event_value('-OUTLETID-', f"['{vidf_mrkr.name}', '{vidf_mrkr.outlet_id}']")
ctr_rec.prepare_devices(f"{collection_id}:{str(tech_obs_log)}", nodes=nodes)

for event, values in wind_gen(window, nodes, timeout=1):
    out = threaded_signals(window, event, values, subj_id, statecolors, stream_ids, inlets, out)

# Run tasks
tasks = [k for k, v in out['values'].items() if "task" in k and v == True]
print(tasks)

if len(tasks):
    running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
    ctr_rec.task_presentation(running_task, subj_id, node=nodes[1])
else:
    sg.PopupError('No task selected')

for event, values in  wind_gen(window, nodes, timeout=3):
    out = threaded_signals(window, event, values, subj_id, statecolors, stream_ids, inlets, out)

# Close
window.write_event_value('Shut Down', "close")
