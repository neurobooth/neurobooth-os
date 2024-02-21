import copy
import logging
import unittest
from os import environ, path
import socket

import neurobooth_os.iout.metadator as meta
import neurobooth_os.iout.stim_param_reader as reader
from neurobooth_os.iout.stim_param_reader import StimulusArgs, _get_cfg_path, _get_param_dictionary
from neurobooth_os.server_stm import prepare_session, create_task_kwargs
from neurobooth_os.tasks.eye_tracker_calibrate import Calibrate


# NOTE: The working directory for executing these tasks must be neurobooth_os
class TestTask(unittest.TestCase):
    stimulus_description: str

    # Integration Test (uses environment variables and local file system)
    def test_read_success(self):
        folder = path.join(environ.get("NB_CONFIG"), "tasks")
        config_path = _get_cfg_path(folder)
        self.assertTrue(isinstance(config_path, str))
        self.assertIsNotNone(config_path)

    def test_io_error(self):
        folder = "wrwqtwwefsdfasq"
        self.assertRaises(IOError, _get_cfg_path, folder)

    # Integration Test (uses environment variables and local file system)
    def test_parse_file(self):
        folder = path.join(environ.get("NB_CONFIG"), "tasks")
        param_dict = _get_param_dictionary("calibration_task_1.yml", folder)
        self.assertIsNotNone(param_dict)

    # Integration Test (uses psychopy windows to construct Task
    def test_validate_task(self):
        folder = path.join(environ.get("NB_CONFIG"), "tasks")
        param_dict = _get_param_dictionary("calibration_task_1.yml", folder)
        test_task = Calibrate(**param_dict)
        self.assertIsNotNone(test_task)

    # Integration Test (uses local file system)
    def test_stimulus_arg_validation(self):

        task_args = StimulusArgs(
            stimulus_id='foo',
            stimulus_description='bar',
            prompt=True,
            num_iterations=1,
            duration=None,
            arg_parser='foo/bar',
            stimulus_file_type='Psychopy',
            stimulus_file='foo/bar',
        )
        self.assertIsNotNone(task_args)

        entries = reader.get_param_dictionary("calibration_task_1.yml", 'tasks')
        task_args2 = StimulusArgs(**entries)
        self.assertIsNotNone(task_args2)

    # Integration Test (uses database)
    def test_instruction_args(self):
        instruction_id = "sacc_horiz_1"
        args = meta._get_instruction_kwargs(instruction_id)
        self.assertIsNone(args.instruction_text)
        self.assertEquals('mp4', args.instruction_filetype)
        self.assertEquals('oculomotor_horizontal_saccades_2022_06_03_v0.6.mp4', args.instruction_file)

    def test_instruction_args_when_no_instructions(self):
        log_path = r"C:\neurobooth\test_data\test_logs"

        collection_id = 'testing'
        database_name = 'mock_neurobooth_1'
        log_task = meta._new_tech_log_dict()
        log_task["subject_id-date"] = "foobar"
        from neurobooth_os.log_manager import make_default_logger
        logger = make_default_logger(log_path, logging.DEBUG, False)
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        socket_1: socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        stm_session, task_log_entry = prepare_session(msg, socket_1, logger)
        print(stm_session)

        task_args = stm_session.task_func_dict['clapping_task']
        print(task_args)
        tsk_fun_obj = copy.copy(task_args.task_constructor_callable)  # callable for Task constructor
        this_task_kwargs = create_task_kwargs(stm_session, task_args)
        print(this_task_kwargs)
        task_args.task_instance = tsk_fun_obj(**this_task_kwargs)

    # Integration test (uses database)
    def test_all_validated_task_args_in_folder(self):
        connection = meta.get_database_connection("neurobooth", False)
        tasks = [
            "ahh_obs_1",
            "altern_hand_mov_obs_1",
            "calibration_obs_1",
            "clapping_test",
            "clapping_test_2",
            "coord_pause_obs_1",
            "coord_pause_obs_2",
            "DSC_obs",
            "finger_nose_demo_obs_1",
            "finger_nose_obs_1",
            "fixation_no_target_obs_1",
            "fixation_target_obs_1",
            "foot_tapping_obs_1",
            "gaze_holding_obs_1",
            "gogogo_obs_1",
            "mouse_demo_obs",
            "hevelius_obs",
            "intro_cog_obs_1",
            "intro_occulo_obs_1",
            "intro_sess_obs_1",
            "intro_speech_obs_1",
            "lalala_obs_1",
            "mememe_obs_1",
            "MOT_obs_1",
            "passage_obs_1",
            "pataka_obs_1",
            "pursuit_obs",
            "saccades_horizontal_obs_1",
            "saccades_vertical_obs_1",
            "sit_to_stand_obs",
            "timing_test_obs",
        ]
        task_params = meta.read_all_task_params()
        for task_id in tasks:
            task_args = meta.build_task(task_params, task_id)
            self.assertIsNotNone(task_args)

    def test_task_args(self):
        task_id = "lalala_obs_1"
        task_params = meta.read_all_task_params()
        task_args = meta.build_task(task_params, task_id)
        self.assertIsNotNone(task_args)

    def test_stm_session_as_dict(self):
        sock: socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        param_dict = meta.read_all_task_params()
        task_id = "saccades_horizontal_obs_1"
        task_args = meta.build_task(param_dict, task_id)
        log_path = r"C:\neurobooth\test_data\test_logs"
        collection_id = 'testing'
        database_name = 'mock_neurobooth_1'
        log_task = meta._new_tech_log_dict()
        log_task["subject_id-date"] = "foobar"
        from neurobooth_os.log_manager import make_default_logger
        logger = make_default_logger(log_path, logging.DEBUG, False)
        msg = f"prepare:{collection_id}:{database_name}:{str(log_task)}"
        stm_session, task_log_entry = prepare_session(msg, sock, logger)
        kwargs = create_task_kwargs(stm_session, task_args)
        print(kwargs)
