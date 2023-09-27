import logging
import os
import shutil
import sys
import unittest

from neurobooth_os.log_manager import make_default_logger, make_db_logger

log_path = r"C:\neurobooth\test_data\test_logs"


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
        """Tests to ensure log handler is closed """
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12")
        db_log.critical("Microphone: Entering LSL Loop", extra={"device": "playstation"})
        logging.shutdown()

    def test_db_logging0(self):
        """Tests logging to database using make_db_logger with session and subject set"""
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12")
        db_log.critical("Microphone: Entering LSL Loop", extra={"device": "playstation"})
        db_log.critical("Another one.", extra={"device": "playstation"})

    def test_db_logging1(self):
        """Tests logging to database using make_db_logger with session and subject set to empty strings"""
        db_log = make_db_logger("", "")
        db_log.critical("No subject or session when log created.", extra={"device": "playstation"})

    def test_db_logging2(self):
        """Tests logging to database with session and subject set to empty strings AFTER being set to values"""
        db_log = make_db_logger("1111111", "1111111_2023_12_25 12:12:12")
        db_log.critical("Subject and session set for the logger", extra={"device": "playstation"})
        db_log = make_db_logger("", "")
        db_log.error("No subject or session for new records")

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


if __name__ == '__main__':
    unittest.main()
