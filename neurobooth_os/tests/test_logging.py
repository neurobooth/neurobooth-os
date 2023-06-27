import logging
import sys
import unittest

from neurobooth_os.logging import make_default_logger


class TestLogging(unittest.TestCase):

    def test_default_logging(self):

        def do_something():
            raise ValueError(":(")

        log_path = r"C:\neurobooth\neurobooth_logs"
        print(log_path)
        make_default_logger(log_path)
        logger = logging.getLogger("default")
        try:
            do_something()
        except Exception as e:
            logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
            logger.critical(e, exc_info=sys.exc_info())


if __name__ == '__main__':
    unittest.main()
