import inspect
import logging
import os
import shutil
import sys
import unittest

from neurobooth_terra import Table

from neurobooth_os.log_manager import make_default_logger, make_db_logger
from neurobooth_os.iout.metadator import get_conn

log_path = r"C:\neurobooth\test_data\test_logs"
database = "mock_neurobooth_1"

subject = "1111111"
session = "1111111_2023_12_25 12:12:12"


def get_records(conn=get_conn(database), where=None):
    """Test utility for querying log_application table. Returns results as a dataframe"""
    table = Table("log_application", conn=conn)
    if where is not None:
        task_df = table.query(where)
    else:
        task_df = table.query()
    print(task_df)
    return task_df


def delete_records(conn=get_conn(database), where=None) -> None:
    """Test utility for querying log_application table. Returns results as a dataframe"""
    table = Table("log_application", conn=conn)
    if where is not None:
        table.delete_row(where)
    else:
        table.delete_row("1=1")


class TestLogging(unittest.TestCase):

    def setUp(self):
        if not os.path.exists(log_path):
            os.makedirs(log_path)

    def tearDown(self):
        logger = logging.getLogger("default")
        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logging.shutdown()
        delete_records()

        if os.path.exists(log_path):
            files = os.listdir(log_path)
            for file in files:
                filename = os.path.join(log_path, file)
                # TODO(larry): uncomment below
                #os.remove(filename)
            #shutil.rmtree(log_path)

    def test_default_logging(self):

        def do_something():
            raise ValueError("Raising a test error. This should get logged.")

        try:
            do_something()
        except Exception as e:
            logger = make_default_logger(log_path)
            logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
            logger.critical(e, exc_info=sys.exc_info())

        filename = os.path.join(log_path, os.listdir(log_path)[0])

        with open(filename, 'r') as file:
            data = file.read()

        self.assertTrue("Exiting" in data)
        self.assertTrue("Traceback" in data)

    def test_db_logging_shutdown(self):
        """Tests to ensure log handler is closed (or at least, doesn't blow up when closing) """
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12")
        db_log.critical("Microphone: Entering LSL Loop", extra={"device": "playstation"})
        logging.shutdown()

    def test_db_logging0(self):
        """Tests logging to database using make_db_logger with session and subject set"""
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12")
        db_log.critical("Microphone: Entering LSL Loop", extra={"device": "playstation"})
        db_log.critical("Another one.", extra={"device": "playstation"})

        df = get_records()
        assert df.iloc[0]["subject_id"] == subject
        assert df.iloc[0]["session_id"] == session
        assert df.iloc[0]["message"] == "Microphone: Entering LSL Loop"

        assert df.iloc[1]["subject_id"] == subject
        assert df.iloc[1]["session_id"] == session
        assert df.iloc[1]["message"] == "Another one."

    def test_db_logging1(self):
        """Tests logging to database using make_db_logger with session and subject set to empty strings"""
        db_log = make_db_logger("", "")
        msg = "No subject or session when log created."
        db_log.critical(msg, extra={"device": "playstation"})

        mod_name = sys.modules[__name__].__name__ + ".py"
        fun_name = inspect.stack()[0][3]

        df = get_records()
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

    def test_db_logging2(self):
        """Tests logging to database with session and subject set to empty strings AFTER being set to values"""
        db_log = make_db_logger(subject, session)
        db_log.critical("Subject and session set for the logger", extra={"device": "playstation"})
        db_log = make_db_logger("", "")
        db_log.error("No subject or session for new records")
        df = get_records()
        assert df.iloc[0]["subject_id"] == subject
        assert df.iloc[0]["session_id"] == session

        assert df.iloc[1]["subject_id"] == ""
        assert df.iloc[1]["session_id"] == ""

    # @unittest.skip("Test requires that DB Connection not succeed (i.e. run outside VPN)")
    def test_db_logging3(self):
        """Tests logging fallback to local file logging.
        """
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12", log_path)
        db_log.critical("Test fallback logging. No DB Connection should be available")

        filename = os.path.join(log_path, os.listdir(log_path)[0])

        with open(filename, 'r') as file:
            data = file.read()
        self.assertTrue("fallback" in data)

    def test_db_logging_with_traceback(self):
        """Evaluate how tracebacks are handled in database.
        """
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12", log_path)
        try:
            raise Exception("This is a test")
        except Exception as Argument:
            db_log.exception("Test db logging with traceback")
        df = get_records()
        assert df.iloc[0]["traceback"] is not None
        assert "This is a test" in df.iloc[0]["traceback"]

    def test_get_records(self):
        """Meta-testing: Tests the get_records and delete_records utility function used in these tests"""
        df = get_records()
        assert(df is not None)
        delete_records()
        df = get_records()
        assert df.empty


if __name__ == '__main__':
    unittest.main()
