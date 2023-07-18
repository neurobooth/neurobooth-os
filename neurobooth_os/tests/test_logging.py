import logging
import os
import shutil
import sys
import unittest

from neurobooth_os.log_manager import make_default_logger

log_path = r"C:\neurobooth\test_data\test_logs"
logger = make_default_logger(log_path)


class TestLogging(unittest.TestCase):

    def tearDown(self):

        handlers = logger.handlers[:]
        for handler in handlers:
            logger.removeHandler(handler)
            handler.close()
        logging.shutdown()

        if os.path.exists(log_path):
            files = os.listdir(log_path)
            for file in files:
                filename = os.path.join(log_path, file)
                os.remove(filename)
            shutil.rmtree(log_path)

    def test_default_logging(self):

        def do_something():
            raise ValueError(":(")

        try:
            do_something()
        except Exception as e:
            logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
            logger.critical(e, exc_info=sys.exc_info())

        filename = os.path.join(log_path, os.listdir(log_path)[0])

        with open(filename, 'r') as file:
            data = file.read()

        self.assertTrue("Exiting" in data)
        self.assertTrue("Traceback" in data)


if __name__ == '__main__':
    unittest.main()
