import unittest

from neurobooth_os.msg.messages import PrepareRequest
from neurobooth_os.server_stm import extract_task_log_entry
from neurobooth_os.util.task_log_entry import TaskLogEntry
import neurobooth_os.iout.metadator as meta
from neurobooth_os.server_stm import prepare_session, _create_tasks


class TestTaskParamReader(unittest.TestCase):

    def test_task_log_entry_creation(self):
        collection_id = 'foo'
        database_name = 'mock_neurobooth_1'
        log_task = meta.new_task_log_dict()
        log_task["subject_id-date"] = "foobar"
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        log_task_entry = extract_task_log_entry(collection_id, msg, database_name)

        self.assertIsInstance(log_task_entry, TaskLogEntry)
        self.assertEquals(log_task_entry.subject_id_date, log_task["subject_id-date"])

    def test_task_log_entry_write(self):
        collection_id = 'foo'
        database_name = 'mock_neurobooth_1'
        log_task = meta.new_task_log_dict()
        log_task["subject_id-date"] = "foobar"
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        log_task_entry = extract_task_log_entry(collection_id, msg, database_name)

        log_task_entry.task_id = "calibration_obs_1"
        log_task_entry.log_session_id = 1381
        log_task_entry.task_notes_file = 'test_notes_file'
        log_task_entry.subject_id = "72"
        log_task_entry.task_output_files = {}
        conn = meta.get_database_connection(database_name)
        log_task_id = meta.make_new_task_row(conn, log_task_entry.subject_id)
        log_task_entry['log_task_id'] = log_task_id
        meta.fill_task_row(log_task_entry, conn)

    # Integration Test (devices, uses database, file system, win ui)
    # Can't run this because of Eyetracker dependency in code
    def test_prepare_session(self):
        log_path = r"C:\neurobooth\test_data\test_logs"

        collection_id = 'testing'
        database_name = 'mock_neurobooth_1'
        log_task = meta.new_task_log_dict()
        log_task["subject_id-date"] = "foobar"
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        stm_session, task_log_entry = prepare_session(msg)
        print(stm_session)
        print(task_log_entry)
        stm_session.shutdown()

    def test_create_tasks(self):
        log_path = r"C:\neurobooth\test_data\test_logs"

        collection_id = 'testing'
        database_name = 'mock_neurobooth'
        subject_id = "72"
        selected_tasks = ['task_1']
        log_task = meta.new_task_log_dict()
        log_task["subject_id-date"] = "foobar"
        msg = PrepareRequest(database_name=database_name, subject_id=subject_id, collection_id=collection_id,
                       selected_tasks=selected_tasks, date="2024-08-28")
        stm_session, task_log_entry = prepare_session(msg)
        calib_instructions, device_log_entry_dict, subj_id, task_calib = _create_tasks(msg, stm_session, task_log_entry)

        stm_session.shutdown()
