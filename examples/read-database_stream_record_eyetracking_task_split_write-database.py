"""
====================
stream record and split mock streams
====================
Use :func:`~neurobooth_os.iout.mock_device_streamer` to generate mock streams and liesl to record.

Only works in Windows or Linux using Wine
"""
# Author: Sheraz Khan <sheraz@khansheraz.com>
#
# License: BSD-3-Clause

# %%
import time
import liesl
import warnings
from pathlib import Path
from h5io import read_hdf5
import neurobooth_os.mock.mock_device_streamer as mocker
from neurobooth_os.iout.marker import marker_stream
from neurobooth_os.iout.split_xdf import get_xdf_name, split_sens_files
from neurobooth_os.tasks import SitToStand
from neurobooth_os.tasks import utils
from neurobooth_os.iout.eyelink_tracker import EyeTracker
from neurobooth_os.layouts import  write_task_notes


warnings.filterwarnings("ignore", category=RuntimeWarning)

print(__doc__)



# %%
# Input Parameters for the database
subject_id = 'Sheraz'
study_id = 'PD_01'
collection_id = 'Hard_v1'
staff_id = 'khan'
mock = True


# %%
# read database
# paramaters = query_database(subject, study, collection, mock)

# tasks = read_collection(collection_id) # Json file, dictionary of dictionaries

#for task, param in tasks.items():
#    task
# %%
# Creating and starting mock streams: read stream_names from database
stream_names = {'MockLSLDevice': 'mock_lsl', 'MockMbient': 'mock_mbient',
                'MockCamera': 'mock_camera', 'marker_stream': 'Marker'}

# Eyetracker like functionality for the Mock devices with a mock flag to specify the mock mode
# single device init with an argument specifying device type
# devices = [key, value for key, value in  stream_names.items()]

dev_stream = mocker.MockLSLDevice(name=stream_names['MockLSLDevice'], nchans=5)
mbient = mocker.MockMbient(name=stream_names['MockMbient']) # Bluetooth mac address
cam = mocker.MockCamera(name=stream_names['MockCamera'])
marker = marker_stream(name=stream_names['marker_stream'])


# %%
# Start mock streams:
cam.start()
dev_stream.start()
mbient.start()
marker.push_sample([f"start_0_{time.time()}"])

# %%
# Setup liesl configuration: parametrs from the database
streamargs = [{'name': stream_name} for stream_name in stream_names.values()]
recording_folder = "~/labrecordings"
subject = "demo_subject"
session = liesl.Session(prefix=subject, streamargs=streamargs, mainfolder=recording_folder)

# %%
# Start recording
task = "sit2stand"
session.start_recording(task)
task_notes = dict()


# %%
# Run task
win = utils.make_win(full_screen=False)
eyetracker = EyeTracker(mock=mock, win=win)
# From database
video_path = 'F:\\vid.mp4'
text_practice = 'Please practice "Sit to Stand" ONE time \n\tPress any button when done'
text_task='Please do "Sit to Stand" FIVE times \n\tPress any button when done'

#Values from database to the task
eyetracker.calibrate()
eyetracker.record()
base_task = SitToStand(marker_outlet=marker, win=win, path_instruction_video=video_path,
                       text_practice_screen=text_practice, text_task=text_task, eyetracker=eyetracker)
utils.run_task(base_task)
eyetracker.stop()
eyetracker.close()
win.close()
if mock:
    task_notes[str(time.time())] = 'subject did good' # this will be done via GUI by RC
    write_task_notes(subject_id, staff_id, task, task_notes)

# %%
# Stop recording
session.stop_recording()

# %%
# Stop mock streams:
cam.stop()
dev_stream.stop()
mbient.stop()


# %%
# getting recorded filename to split
final_fname = get_xdf_name(session, task)

# %%
# Split xdf file per sensor
files = split_sens_files(final_fname)


# %%
# read splitted h5 files
streams = [read_hdf5(file) for file in files]

# %%
# write database
# paramaters = write_database(session, files)



