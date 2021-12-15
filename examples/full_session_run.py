
import threading
import sys 
import PySimpleGUI as sg
from time import sleep as tsleep
from datetime import datetime

import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.netcomm import get_messages_to_ctr, node_info, NewStdout
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout import marker_stream
from neurobooth_os.gui import _process_received_data, ctr_event_handler
from neurobooth_os.layouts import _main_layout, _win_gen
import neurobooth_os.iout.metadator as meta


def event_listener(window, timeout=1):
    while True:
        event, values = window.read(timeout)
        yield event, values

# Define parameters
remote = True
database_name = "neurobooth"  # "mock_neurobooth"
collection_id = "mvp_030"  # "mock_collection"  # Define mock with tasks to run
sess_info = {"subject_id": "69",  #"test_nogui",
             "staff_id":"AN", 
             '_tasks_': "mock_task_1",
             'first_name': 'Prince',
             'last_name': 'Philips'}

nodes = ('dummy_acq', 'dummy_stm')

tech_obs_log = meta._new_tech_log_dict()
tech_obs_log["study_id"] = 'study1'
tech_obs_log["collection_id"] = collection_id
tech_obs_log["staff_id"] = sess_info['staff_id']
tech_obs_log["subject_id"] = sess_info['subj_id']
study_id_date = f'{sess_info["subj_id"]}_{datetime.now().strftime("%Y-%m-%d")}'
tech_obs_log["study_id-date"] = study_id_date
subj_id = sess_info['subj_id']

# Get DB connexion
if remote:
    ctr_node = "dummy_ctr"
    nodes = ('dummy_acq', 'dummy_stm')
else:
    ctr_node = "control"
    nodes = ("acquisition", "presentation")
    
conn = meta.get_conn(remote=remote, database=database_name)

# Create mock CTR
window = _win_gen(_main_layout, sess_info, True)
event, values = window.read(.1)
ctr_host, ctr_port = node_info(ctr_node)   
callback, callback_args = _process_received_data, window    
server_thread = threading.Thread(target=get_messages_to_ctr,
                                    args=(callback, remote, ctr_host, ctr_port, callback_args,),
                                    daemon=True)
server_thread.start()
tsleep(.3)

if remote:
    # Rerout stdout to dummy_ctr and print in terminal
    sys.stdout = NewStdout("mock",  target_node=ctr_node, terminal_print=True)

# Create servers
ctr_rec.start_servers(nodes=nodes, remote=remote, conn=conn)
tsleep(.3)

# automatically run session
stream_ids, inlets,  = {}, {}
out = dict(exit_flag=None,  # where to break
    break_ = False,  # break loop if True                
    obs_log_id = None, 
    t_obs_id = None, 
    task_id = None,
    )
        
statecolors = {"-init_servs-": ["green", "yellow"],
                "-Connect-": ["green", "yellow"],
               }

# Prepare devices
vidf_mrkr = marker_stream('videofiles')
window.write_event_value('-OUTLETID-', f"['{vidf_mrkr.name}', '{vidf_mrkr.outlet_id}']")
ctr_rec.prepare_devices(f"{collection_id}:{str(tech_obs_log)}", nodes=nodes)
out["vidf_mrkr"] = vidf_mrkr

out['exit_flag'] ='prepared'
for event, values in event_listener(window, timeout=1):
    out = ctr_event_handler(window, event, values, conn, study_id_date, statecolors, stream_ids, inlets, out)
    if out["break_"]:
        print("exiting prepare loop")
        out["break_"] = False
        break
        
# Get tasks
tasks_obs = meta.get_tasks(collection_id, conn)
tasks = []
for task in tasks_obs:
    task_id, *_ = meta._get_task_param(task, conn)
    tasks.append(task_id)
print(tasks)

tasks = ['intro_occulo_task_1', 'pursuit_task_1', 'intro_cog_task_1', 'sit_to_stand_task_1']

if len(tasks):
    running_task = "-".join(tasks)  # task_name can be list of task1-task2-task3
    ctr_rec.task_presentation(running_task, subj_id, node=nodes[1])
else:
    print('No task selected')

# Present tasks
out['exit_flag'] ='task_end'
# remove calibration and intro tasks as wont signal task finished
tasks_no_introcal = [ t for t in tasks if  not any(x for x in ['calibration_task', "intro_"] if x in t)]
for task in tasks_no_introcal:
    for event, values in  event_listener(window, timeout=1):
        out = ctr_event_handler(window, event, values, conn, study_id_date, statecolors, stream_ids, inlets, out)
        if out["break_"] == True:
            out["break_"] = False
            print(f'out task {task}')
            break

# Close
ctr_rec.shut_all(nodes=nodes)
window.close()