from neurobooth_os.iout.metadator import get_conn
from neurobooth_os.iout.split_xdf import create_h5_from_csv

conn = get_conn()
# location of the csv file containing path filename and task ID
dont_split_xdf_fpath = "C:/neurobooth"
create_h5_from_csv(dont_split_xdf_fpath, conn)
