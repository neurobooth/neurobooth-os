from neurobooth_os.iout.metadator import get_database_connection
from neurobooth_os.iout.split_xdf import postprocess_xdf_split
import neurobooth_os.config as config

config.load_config()
postprocess_xdf_split(
    "C:/neurobooth/split_tohdf5.csv",
    get_database_connection()
)
