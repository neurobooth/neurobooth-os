import inspect
import logging
import sys
import unittest

from neurobooth_os.log_manager import make_task_param_logger
import db_test_utils
from db_test_utils import get_connection, get_records, delete_records, TEST_CONNECTION

subject = "0000000"
session = "0000000_2023_12_25 12:12:12"
table_name = "log_task_param"

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
        tp_log = make_task_param_logger(subject, session)
        tp_log.warning("", extra={"key": "foo", "value": "bar"})
        tp_log.warning("", extra={"key": "fizz", "value": "buzz"})

        df = get_records(table_name)
        print(df)
        assert df.iloc[0]["subject_id"] == subject
        assert df.iloc[0]["session_id"] == session
        assert df.iloc[0]["key"] == "foo"
        assert df.iloc[0]["value"] == "bar"

        assert df.iloc[1]["subject_id"] == subject
        assert df.iloc[1]["session_id"] == session
        assert df.iloc[1]["key"] == "fizz"
        assert df.iloc[1]["value"] == "buzz"

    def test_task_param_logging_1(self):
        """Tests logging to database using make_db_logger with session and subject set to empty strings"""
        db_log = make_task_param_logger("", "")
        msg = "No subject or session when log created."
        db_log.critical(msg, extra={"device": "playstation"})

        mod_name = sys.modules[__name__].__name__ + ".py"
        fun_name = inspect.stack()[0][3]

        df = get_records(table_name)
        assert df.shape[0] == 1
        assert df.iloc[0]["log_level"].upper() == "CRITICAL"
        assert df.iloc[0]["device"] == "playstation"
        assert df.iloc[0]["subject_id"] == ""
        assert df.iloc[0]["session_id"] == ""
        assert df.iloc[0]["server_type"] == "control"
        assert df.iloc[0]["server_id"] != ""
        assert df.iloc[0]["server_time"] is not None
        assert df.iloc[0]["filename"] == mod_name
        assert df.iloc[0]["function"] == fun_name
        assert df.iloc[0]["line_no"] >= 1
        assert df.iloc[0]["message"] == msg
        assert df.iloc[0]["traceback"] is None

    def test_task_param_logging_2(self):
        """Tests logging to database with session and subject set to empty strings AFTER being set to values"""
        log = make_task_param_logger(subject, session)
        log.info("", extra={"key": "foo", "value": "bar"})
        log = make_task_param_logger("", "")
        log.info("No subject or session for new records")
        df = get_records(table_name)
        assert df.iloc[0]["subject_id"] == subject
        assert df.iloc[0]["session_id"] == session

        assert df.iloc[1]["subject_id"] == ""
        assert df.iloc[1]["session_id"] == ""


if __name__ == '__main__':
    unittest.main()
