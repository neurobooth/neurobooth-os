import logging
import unittest

from neurobooth_os.iout.task_param_reader import TaskArgs
from neurobooth_os.server_stm import extract_task_log_entry
from neurobooth_os.util.task_log_entry import TaskLogEntry
import neurobooth_os.iout.metadator as meta
import socket
from neurobooth_os.server_stm import prepare_session


class TestTaskParamReader(unittest.TestCase):

    def test_task_log_entry_creation(self):
        collection_id = 'foo'
        database_name = 'mock_neurobooth_1'
        log_task = meta._new_tech_log_dict()
        log_task["subject_id-date"] = "foobar"
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        log_task_entry = extract_task_log_entry(collection_id, msg, database_name)

        self.assertIsInstance(log_task_entry, TaskLogEntry)
        self.assertEquals(log_task_entry.subject_id_date, log_task["subject_id-date"])

    def test_task_log_entry_write(self):
        collection_id = 'foo'
        database_name = 'mock_neurobooth_1'
        log_task = meta._new_tech_log_dict()
        log_task["subject_id-date"] = "foobar"
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        log_task_entry = extract_task_log_entry(collection_id, msg, database_name)

        log_task_entry.task_id = "calibration_obs_1"
        log_task_entry.log_session_id = 1381
        log_task_entry.task_notes_file = 'test_notes_file'
        log_task_entry.subject_id = "72"
        log_task_entry.task_output_files = {}
        conn = meta.get_conn(database_name, False)
        log_task_id = meta.make_new_task_row(conn, log_task_entry.subject_id)
        print(log_task_id)
        meta.fill_task_row(log_task_id, log_task_entry, conn)

    # Integration Test (devices, uses database, file system, win ui)
    # Can't run this because of Eyetracker dependency in code
    def test_prepare_session(self):
        log_path = r"C:\neurobooth\test_data\test_logs"

        collection_id = 'testing'
        database_name = 'mock_neurobooth_1'
        log_task = meta._new_tech_log_dict()
        log_task["subject_id-date"] = "foobar"
        from neurobooth_os.log_manager import make_default_logger
        logger = make_default_logger(log_path, logging.DEBUG, False)
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        sock: socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        stm_session, task_log_entry = prepare_session(msg, sock, logger)
        print(stm_session)
        print(task_log_entry)
        stm_session.shutdown()

    def test_create_task_kwargs(self):
        log_path = r"C:\neurobooth\test_data\test_logs"

        collection_id = 'testing'
        database_name = 'mock_neurobooth_1'
        log_task = meta._new_tech_log_dict()
        log_task["subject_id-date"] = "foobar"
        from neurobooth_os.log_manager import make_default_logger
        logger = make_default_logger(log_path, logging.DEBUG, False)
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        stm_session, task_log_entry = prepare_session(msg, logger)
        print(stm_session)
        print(stm_session.as_dict())

        task_args: TaskArgs = TaskArgs()
        stm_session.shutdown()
