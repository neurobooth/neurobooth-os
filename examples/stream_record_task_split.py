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
from neurobooth_os.iout.split_xdf import split, get_xdf_name
from neurobooth_os.tasks import SitToStand
from neurobooth_os.tasks import utils


warnings.filterwarnings("ignore", category=RuntimeWarning)

print(__doc__)

# %%
# Creating and starting mock streams:
stream_names = {'MockLSLDevice': 'mock_lsl', 'MockMbient': 'mock_mbient',
                'MockCamera': 'mock_camera', 'marker_stream': 'Marker'}
dev_stream = mocker.MockLSLDevice(name=stream_names['MockLSLDevice'], nchans=5)
mbient = mocker.MockMbient(name=stream_names['MockMbient'])
cam = mocker.MockCamera(name=stream_names['MockCamera'])
marker = marker_stream(name=stream_names['marker_stream'])


# %%
# Start mock streams:
cam.start()
dev_stream.start()
mbient.start()
marker.push_sample([f"start_0_{time.time()}"])

# %%
# Setup liesl configuration:
streamargs = [{'name': stream_name} for stream_name in stream_names.values()]
recording_folder = "~/labrecordings"
subject = "demo_subject"
session = liesl.Session(prefix=subject, streamargs=streamargs, mainfolder=recording_folder)

# %%
# Start recording
task = "sit2stand"
session.start_recording(task)

# %%
# Run task
win = utils.make_win(full_screen=False)
# From database
video_path = 'F:\\vid.mp4'
text_practice = 'Please practice "Sit to Stand" ONE time \n\tPress any button when done'
text_task='Please do "Sit to Stand" FIVE times \n\tPress any button when done'

#Values from database to the task
base_task = SitToStand(marker_outlet=marker, win=win, path_instruction_video=video_path,
                       text_practice_screen=text_practice, text_task=text_task)
utils.run_task(base_task)
win.close()

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
files = split(final_fname)


# %%
# read first split h5 file
marker, stream = read_hdf5(files[0])


