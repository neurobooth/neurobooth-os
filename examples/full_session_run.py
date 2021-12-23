"""Run full session without PySimpleGUI."""

from neurobooth_os.netcomm import node_info
import neurobooth_os.iout.metadator as meta
from neurobooth_os.gui import (_find_subject, _select_subject, _get_tasks,
                               _save_session, _get_collections,
                               _start_ctr_server, _start_servers,
                               _prepare_devices, _start_task_presentation,
                               _update_button_status, _create_lsl_inlet,
                               _start_lsl_session, _record_lsl,
                               _get_ports)
from neurobooth_os.mock import MockWindow

remote = True
database, nodes, host_ctr, port_ctr = _get_ports(remote, database='neurobooth')

steps = list()
stream_ids, inlets = dict(), dict()
tech_obs_log = meta._new_tech_log_dict()

start_window = MockWindow(['first_name', 'last_name', 'dob', 'collection_id',
                           'tasks'])
main_window = MockWindow(['-init_servs-', '-Connect-', 'Start', 'task_title',
                          'task_running'])

conn = meta.get_conn(remote=remote, database=database)

####### START WINDOW #########

first_name, last_name = "Anna", "Luddy"
subject_df = _find_subject(start_window, conn, first_name, last_name)
first_name, last_name, subject_id = _select_subject(start_window, subject_df)

study_id = 'mock_study'
tech_obs_log["study_id"] = study_id
collection_ids = _get_collections(start_window, conn, study_id)

collection_id = collection_ids[0]
tasks = _get_tasks(start_window, conn, collection_id)

staff_id = 'AN'
sess_info = _save_session(start_window,
                          tech_obs_log, staff_id,
                          subject_id, first_name, last_name, tasks)

####### MAIN WINDOW #########

_start_ctr_server(main_window, host_ctr, port_ctr, sess_info, remote=remote)
_start_servers(main_window, conn, nodes, remote=remote)
vidf_mrkr, _, _ = _prepare_devices(main_window, nodes, collection_id,
                                   tech_obs_log)

_start_task_presentation(main_window, [tasks], sess_info['subject_id'], steps,
                         node=nodes[1])

while True:
    event, value = main_window.read(0.5)

    if event == 'task_initiated':
        task_id, t_obs_id, obs_log_id, tsk_strt_time = eval(value)
        rec_fname = _record_lsl(main_window, session, subject_id, task_id,
                                t_obs_id, obs_log_id, tsk_strt_time)

    elif event == '-update_butt-':
        session = _start_lsl_session(main_window, inlets)

    elif event == '-OUTLETID-':
        _create_lsl_inlet(stream_ids, value, inlets)

    elif event == "-new_filename-":
        vidf_mrkr.push_sample([value])
        print(f"pushed videfilename mark {value}")
