import unittest

from neurobooth_os.iout import metadator as meta
from neurobooth_os.util.task_log_entry import TaskLogEntry


class TestMetadator(unittest.TestCase):

    def test_read_sensors(self):
        sens_dict = meta.read_sensors()
        print(sens_dict)

    def test_read_devices(self):
        sens_dict = meta.read_devices()
        print(sens_dict)

    def test_read_instructions(self):
        sens_dict = meta.read_instructions()
        print(sens_dict)

    def test_read_stimuli(self):
        sens_dict = meta.read_stimuli()
        print(sens_dict)

    def test_read_tasks(self):
        a_dict = meta.read_tasks()
        print(a_dict)

    def test_read_all_task_params(self):
        a_dict = meta._read_all_task_params()
        print(a_dict["tasks"])
        print(a_dict["stimuli"])
        print(a_dict["instructions"])
        print(a_dict["devices"])
        print(a_dict["sensors"])

    def test_build_tasks_for_collection(self):
        import pprint

        collection_id = 'mvp_030'
        task_dict = meta.build_tasks_for_collection(collection_id)
        self.assertIsNotNone(task_dict)
        pursuit = task_dict['pursuit_obs']
        pprint.pp(pursuit.dump_filtered())

    def test_read_studies(self):
        self.assertIsNotNone(meta.read_studies())

    def test_get_stimulus_id(self):
        print(meta.get_stimulus_id("altern_hand_mov_obs_1"))
        self.assertIsNotNone(meta.get_stimulus_id("altern_hand_mov_obs_1"))

    def test_read_collections(self):
        print(meta.read_collections())
        self.assertIsNotNone(meta.read_collections())

    def test_read_collection_ids(self):
        self.assertIsNotNone(meta.get_collection_ids("study1"))

    def test_get_task_ids_for_collection(self):
        print(meta.get_task_ids_for_collection("testing"))
        self.assertIsNotNone(meta.get_task_ids_for_collection("testing"))

    def test_task_addition( self):
        conn = meta.get_database_connection(database='mock_neurobooth_1', validate_config_paths=False)
        subj_id = "100057"
        task_id = meta.make_new_task_row(conn, subj_id)
        if task_id is None:
            task_id = '1071'

        vals_dict = meta._new_tech_log_dict()
        vals_dict["subject_id"] = subj_id
        vals_dict["log_session_id"] = 1071
        vals_dict["study_id"] = "mock_study"
        vals_dict["subject_id_date"] = f"{subj_id}-2021-12-21"
        vals_dict["task_id"] = "mock_obs_1"
        vals_dict["staff_id"] = "mocker"
        vals_dict["event_array"] = ['event:datestamp']
        vals_dict["collection_id"] = "mock_collection"
        vals_dict["site_id"] = "mock_site"
        vals_dict["task_output_files"] = ['000000_2024-04-11_MOT_results_v2.csv',
                                          '000000_2024-04-11_MOT_outcomes_v2.csv',
                                          '000000_2024-04-11_MOT_results_v2_rep-1.csv',
                                          '000000_2024-04-11_MOT_outcomes_v2_rep-1.csv']
        vals_dict['log_task_id'] = task_id

        entry = TaskLogEntry(**vals_dict)

        meta.fill_task_row(entry, conn)
