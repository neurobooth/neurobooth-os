"""Run full session without PySimpleGUI."""
import time
from datetime import datetime
from neurobooth_os.netcomm import node_info
import neurobooth_os.iout.metadator as meta
import neurobooth_os.main_control_rec as ctr_rec
from neurobooth_os.gui import (_find_subject, _select_subject, _get_tasks,
                               _save_session, _get_collections,
                               _start_ctr_server, _start_servers,
                               _prepare_devices, _start_task_presentation,
                               _update_button_status, _create_lsl_inlet,
                               _start_lsl_session, _record_lsl,
                               _get_ports, _stop_lsl_and_save)
from neurobooth_os.mock import MockWindow

####### PARAMETERS #########
remote = False
database = 'neurobooth'
staff_id = 'AN'
first_name, last_name = "Anna", "Luddy"
study_id = "study1" # 'mock_study'
collection_id = "mvp_030" 


####### PREPARE WINDOWS #########
database, nodes, host_ctr, port_ctr = _get_ports(remote, database=database)

steps = list()
stream_ids, inlets = dict(), dict()
log_task = meta._new_tech_log_dict()
log_sess = meta._new_session_log_dict()
log_sess['staff_id'] = staff_id

start_window = MockWindow(['first_name', 'last_name', 'dob', 'collection_id',
                           'tasks', 'select_subject'])
main_window = MockWindow(['-init_servs-', '-Connect-', 'Start', 'task_title',
                          'task_running'])

conn = meta.get_conn(remote=remote, database=database)

####### START WINDOW #########
subject_df = _find_subject(start_window, conn, first_name, last_name)
first_name, last_name, subject_id = _select_subject(start_window, subject_df)
log_sess['subject_id'] = subject_id
log_task['subject_id-date'] =  f'{subject_id}_{datetime.now().strftime("%Y-%m-%d")}'
log_sess["study_id"] = study_id
collection_ids = _get_collections(start_window, conn, study_id)

log_sess["collection_id"] = collection_id

tasks = _get_tasks(start_window, conn, collection_id)

sess_info = _save_session(start_window,
                          log_task, staff_id,
                          subject_id, first_name, last_name, tasks)

####### MAIN WINDOW #########
_start_ctr_server(main_window, host_ctr, port_ctr, remote=remote)
if not remote:
    time.sleep(2)
_start_servers(main_window, conn, nodes, remote=remote)
if not remote:
    time.sleep(5)
vidf_mrkr, _, _ = _prepare_devices(main_window, nodes, collection_id,
                                   log_task, database=database)

# Start LSL streams
n_nodes_ready = 0
while True:
    event, value = main_window.read(0.1)
    if event == '-OUTLETID-':
        _create_lsl_inlet(stream_ids, value, inlets)

    elif event == "-update_butt-":
        n_nodes_ready += 1
        if n_nodes_ready == 2:
            session_id = meta._make_session_id(conn, log_sess)
            session = _start_lsl_session(main_window, inlets, sess_info['subject_id_date'])
            break

tasks_selected = tasks.split(", ")
_start_task_presentation(main_window, tasks_selected, sess_info['subject_id'], session_id, steps,
                         node=nodes[1])

n_tasks_finished = 0
while True:
    event, value = main_window.read(0.1)

    if event == 'task_initiated':
        task_id, t_obs_id, obs_log_id, tsk_strt_time = eval(value)
        rec_fname = _record_lsl(main_window, session, sess_info['subject_id_date'], task_id,
                                t_obs_id, obs_log_id, tsk_strt_time, nodes[1])

    elif event == "-new_filename-":
        vidf_mrkr.push_sample([value])
        print(f"pushed videfilename mark {value}")

    elif event == 'task_finished':
        task_id = value
        _stop_lsl_and_save(main_window, session, conn,
                           rec_fname, task_id, obs_log_id, t_obs_id, sess_info['subject_id_date'])
        if task_id not in ['calibration_task', "intro_"]:
            n_tasks_finished += 1

    elif n_tasks_finished == len(tasks_selected):
        ctr_rec.shut_all(nodes=nodes)
        break
