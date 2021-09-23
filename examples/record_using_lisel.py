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
import neurobooth_os.iout.mock_device_streamer as mocker
from neurobooth_os.iout.marker import marker_stream

print(__doc__)

# %%
# Creating and starting mock streams:
dev_stream = mocker.MockLSLDevice(name="mock_lsl", nchans=5)
mbient = mocker.MockMbient(name="mock_mbient")
cam = mocker.MockCamera(name="mock_camera")
marker = marker_stream()


# %%
# Start mock streams:
cam.start()
dev_stream.start()
mbient.start()
marker.push_sample(["Stream-mark"])

# %%
# Setup liesl configuration:

streamargs = [{'name': "mock_lsl"},
              {'name': "mock_mbient"},
              {'name': "mock_camera"},
              {'name': "Marker"}]
recording_folder = "~/labrecordings"
session = liesl.Session(prefix="VvNn",
                        streamargs=streamargs, mainfolder=recording_folder)

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

