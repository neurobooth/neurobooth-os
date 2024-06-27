from neurobooth_os.iout.metadator import get_database_connection
from neurobooth_os.iout.split_xdf import postprocess_xdf_split
import logging
from neurobooth_os.log_manager import make_db_logger
import neurobooth_os.config as config

config.load_config()
make_db_logger()  # Initialize logging to default
postprocess_xdf_split(
    config.neurobooth_config.split_xdf_backlog,
    get_database_connection()
)
logging.shutdown()
