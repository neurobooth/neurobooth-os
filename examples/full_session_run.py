from neurobooth_os.netcomm import node_info
import neurobooth_os.iout.metadator as meta
from neurobooth_os.gui import (_find_subject, _select_subject, _get_tasks,
                               _save_session, _get_collections,
                               _start_ctr_server, _start_servers,
                               _prepare_devices, _start_task_presentation)

# Manually define parameters
remote = True

# Get DB connexion
if remote:
    database = "mock_neurobooth"
    nodes = ('dummy_acq', 'dummy_stm')
    host_ctr, port_ctr = node_info("dummy_ctr")
else:
    nodes = ('acquisition', 'presentation')
    host_ctr, port_ctr = node_info("control")

# collection_id = "mvp_030"  # "mock_collection"  # Define mock with tasks to run

steps = list()
tech_obs_log = meta._new_tech_log_dict()

class FakeGUIElement(dict):
    def get_indexes(self):
        return 0
    def Update(self, button_color):
        pass

class FakeWindow(dict):
    def read(self, arg1):
        return (0, 0)
    def write_event_value(self, arg1, arg2):
        return
    def close(self):
        pass

fake_gui_element = FakeGUIElement()
fake_window1 = FakeWindow(
    {'dob': fake_gui_element, 'first_name': fake_gui_element,
     'last_name': fake_gui_element, 'collection_id': fake_gui_element,
     'tasks': fake_gui_element})

fake_window2 = FakeWindow(
    {'-init_servs-': fake_gui_element, '-Connect-': fake_gui_element,
     'Start': fake_gui_element}
)

conn = meta.get_conn(remote=remote, database=database)

first_name, last_name = "Anna", "Luddy"
subject_df = _find_subject(fake_window1, conn, first_name, last_name)
first_name, last_name, subject_id = _select_subject(fake_window1, subject_df)

study_id = 'mock_study'
tech_obs_log["study_id"] = study_id
collection_ids = _get_collections(fake_window1, conn, study_id)

collection_id = collection_ids[0]
tasks = _get_tasks(fake_window1, conn, collection_id)

staff_id = 'AN'
sess_info = _save_session(fake_window1,
                          tech_obs_log, staff_id,
                          subject_id, first_name, last_name, tasks)
window = _start_ctr_server(host_ctr, port_ctr, sess_info, remote=remote)
window.close()

_start_servers(fake_window2, conn, nodes, remote=True)
vidf_mrkr, _, _ = _prepare_devices(fake_window2, nodes, collection_id,
                                   tech_obs_log)
_start_task_presentation(fake_window2, tasks, sess_info['subject_id'], steps,
                         node=nodes[1])
