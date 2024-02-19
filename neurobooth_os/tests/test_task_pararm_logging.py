import logging
import unittest

import db_test_utils
from db_test_utils import get_connection, get_records, delete_records
import neurobooth_os.iout.metadator as meta

table_name = "log_task_param"
stimulus_id = "calibration_task_1"
task_id = "calibration_obs_1"
log_task_id = "tech_log_885"


class TestLogging(unittest.TestCase):

    def setUp(self):
        if db_test_utils.TEST_CONNECTION is not None:
            db_test_utils.TEST_CONNECTION.close()
        db_test_utils.TEST_CONNECTION = get_connection()

    def tearDown(self):
        delete_records(table_name)
        logger = logging.getLogger()
        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logging.shutdown()

        if db_test_utils.TEST_CONNECTION is not None:
            db_test_utils.TEST_CONNECTION.close()
            db_test_utils.TEST_CONNECTION = None

    def test_task_logging0(self):
        """Tests logging to database using make_db_logger with session and subject set"""
        key = 'key'
        value = 'value'
        value_type = 'str'
        args = {
            "log_task_id": log_task_id,
            "stimulus_id": stimulus_id,
            "key": key,
            "value": value,
            "value_type": value_type,
        }
        meta._log_task_parameter(db_test_utils.TEST_CONNECTION, args)

        df = get_records(table_name)
        assert df.iloc[0]["stimulus_id"] == stimulus_id
        assert df.iloc[0]["log_task_id"] == log_task_id
        assert df.iloc[0]["key"] == key
        assert df.iloc[0]["value"] == value
        assert df.iloc[0]["value_type"] == value_type

    def test_task_logging2(self):
        """Tests logging to database using make_db_logger with session and subject set"""

        param_dict = {"foo": "bar", "fizz": "buzz"}
        task_func_dict = meta.build_tasks_for_collection('testing')

        meta.log_task_params(db_test_utils.TEST_CONNECTION, stimulus_id, log_task_id,
                             dict(task_func_dict[task_id].stim_args))

        meta.log_task_params(db_test_utils.TEST_CONNECTION,
                             stimulus_id=stimulus_id,
                             log_task_id=log_task_id,
                             task_param_dictionary=param_dict)
        df = get_records(table_name)
        assert df.iloc[0]["stimulus_id"] == stimulus_id
        assert df.iloc[0]["log_task_id"] == log_task_id
        assert df.iloc[0]["key"] == "foo"
        assert df.iloc[0]["value"] == "bar"
        assert df.iloc[0]["value_type"] == str(type(param_dict["foo"]))

        assert df.iloc[1]["stimulus_id"] == stimulus_id
        assert df.iloc[1]["log_task_id"] == log_task_id
        assert df.iloc[1]["key"] == "fizz"
        assert df.iloc[1]["value"] == param_dict["fizz"]
        assert df.iloc[1]["value_type"] == str(type(param_dict["fizz"]))


if __name__ == '__main__':
    unittest.main()
