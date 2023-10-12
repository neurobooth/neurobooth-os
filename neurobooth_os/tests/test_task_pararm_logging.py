import logging
import unittest

from neurobooth_os.log_manager import make_task_param_logger
import db_test_utils
from db_test_utils import get_connection, get_records, delete_records

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
        assert df.iloc[0]["subject_id"] == subject
        assert df.iloc[0]["session_id"] == session
        assert df.iloc[0]["key"] == "foo"
        assert df.iloc[0]["value"] == "bar"

        assert df.iloc[1]["subject_id"] == subject
        assert df.iloc[1]["session_id"] == session
        assert df.iloc[1]["key"] == "fizz"
        assert df.iloc[1]["value"] == "buzz"


if __name__ == '__main__':
    unittest.main()
