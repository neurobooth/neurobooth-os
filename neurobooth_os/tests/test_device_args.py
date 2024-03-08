import unittest
from typing import Dict

import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.camera_intel import VidRec_Intel
from neurobooth_os.iout.stim_param_reader import DeviceArgs


class TestTask(unittest.TestCase):
    stimulus_description: str

    # Integration Test (uses environment variables and local file system)
    def test_read_success(self):
        devices: Dict[str, DeviceArgs] = meta.read_devices()
        for device in devices.values():
            if "Intel" in device.device_id:
                print(device)
                sensors = meta.read_sensors()
                for sensor_id in device.sensor_ids:
                    device.sensor_array.append(sensors[sensor_id])
                print(device)
                VidRec_Intel(device)
