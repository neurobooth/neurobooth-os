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
from pathlib import Path
from h5io import read_hdf5
import neurobooth_os.mock.mock_device_streamer as mocker
from neurobooth_os.iout.marker import marker_stream
from neurobooth_os.iout.split_xdf import split_sens_files, get_xdf_name

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
session = liesl.Session(prefix=subject,
                        streamargs=streamargs, mainfolder=recording_folder)

# %%
# Run stream for 1 minutes, send trigger every 10 second and record:
task = "mock_streams"
session.start_recording(task)
t_end = time.time() + 60 * 1
while time.time() < t_end:
    time.sleep(10 - time.time() % 10)
    marker.push_sample([f"start_0_{time.time()}"])

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
# read first split h5 file
marker, stream = read_hdf5(files[0])


