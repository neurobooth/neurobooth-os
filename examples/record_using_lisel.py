"""
====================
record mock streams
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
import neurobooth_os.mock.mock_device_streamer as mocker
from neurobooth_os.iout.marker import marker_stream

print(__doc__)

# %%
# Creating and starting mock streams:
stream_names = {'MockLSLDevice': 'mock_lsl', 'MockMbient': 'mock_mbient',
                'MockCamera': 'mock_camera', 'marker_stream': 'Marker', 'videofiles': 'videofiles'}
dev_stream = mocker.MockLSLDevice(name=stream_names['MockLSLDevice'], nchans=5)
mbient = mocker.MockMbient(name=stream_names['MockMbient'])
cam = mocker.MockCamera(name=stream_names['MockCamera'])
marker = marker_stream(name=stream_names['marker_stream'])

# %%
# Setup liesl configuration:
streamargs = [{'name': stream_name} for stream_name in stream_names.values()]
recording_folder = "~/labrecordings"
subject = "demo_subject"
session = liesl.Session(prefix=subject,
                        streamargs=streamargs, mainfolder=recording_folder)

# %%
# Start mock streams:
cam.start()
dev_stream.start()
mbient.start()
marker.push_sample(["Stream-mark"])

# %%
# Run stream for 1 minutes, send trigger every 10 second and record:

session.start_recording()

t_end = time.time() + 60 * 1
while time.time() < t_end:
    time.sleep(10 - time.time() % 10)
    marker.push_sample(["Stream-mark"])

session.stop_recording()

# %%
# Stop mock streams:
cam.stop()
dev_stream.stop()
mbient.stop()

