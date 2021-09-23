"""
=====================
Generate mock streams
=====================
Use :func:`~neurobooth_os.iout.mock_device_streamer` to generate mock streams.
"""
# Author: Sheraz Khan <sheraz@khansheraz.com>
#
# License: BSD-3-Clause

# %%
import time
import neurobooth_os.iout.mock_device_streamer as mocker
from neurobooth_os.iout.marker import marker_stream

print(__doc__)

# %%
# Create mock streams:
dev_stream = mocker.MockLSLDevice(name="mock", nchans=5)
mbient = mocker.MockMbient()
cam = mocker.MockCamera()
marker = marker_stream()

# %%
# Start mock streams:
cam.start()
dev_stream.start()
mbient.start()

# %%
# Run stream for 10 minutes and send trigger every 10 second:
t_end = time.time() + 60 * 10
while time.time() < t_end:
    time.sleep(10 - time.time() % 10)
    marker.push_sample([f"Stream-mark"])

# %%
# Stop mock streams:
cam.stop()
dev_stream.stop()
mbient.stop()
