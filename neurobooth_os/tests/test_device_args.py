import unittest
from typing import Dict

import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.camera_intel import VidRec_Intel
from neurobooth_os.iout.eyelink_tracker import EyeTracker
from neurobooth_os.iout.flir_cam import VidRec_Flir
from neurobooth_os.iout.mbient import Mbient
from neurobooth_os.iout.microphone import MicStream
from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.tasks.utils import make_win

class TestTask(unittest.TestCase):
    stimulus_description: str

    # Integration Test (uses environment variables and local file system)
    def test_intel_camera_setup(self):
        devices: Dict[str, DeviceArgs] = meta.read_devices()
        for device in devices.values():
            if "Intel" in device.device_id:
                print(device)
                sensors = meta.read_sensors()
                for sensor_id in device.sensor_ids:
                    device.sensor_array.append(sensors[sensor_id])
                print(device)
                VidRec_Intel(device)

    # Integration Test (uses environment variables and local file system)
    def test_mbient_device_setup(self):
        devices: Dict[str, DeviceArgs] = meta.read_devices()
        for device in devices.values():
            if "Mbient" in device.device_id:
                print(device)
                sensors = meta.read_sensors()
                for sensor_id in device.sensor_ids:
                    device.sensor_array.append(sensors[sensor_id])
                print(device)
                Mbient(device)

    def test_flir_cam_setup(self):
        devices: Dict[str, DeviceArgs] = meta.read_devices()
        for device in devices.values():
            if "FLIR" in device.device_id:
                print(device)
                sensors = meta.read_sensors()
                for sensor_id in device.sensor_ids:
                    device.sensor_array.append(sensors[sensor_id])
                print(device)
                VidRec_Flir(device)

    def test_mic_yeti_setup(self):
        devices: Dict[str, DeviceArgs] = meta.read_devices()
        for device in devices.values():
            if "Yeti" in device.device_id:
                print(device)
                sensors = meta.read_sensors()
                for sensor_id in device.sensor_ids:
                    device.sensor_array.append(sensors[sensor_id])
                print(device)
                MicStream(device)

    def test_eyelink_setup(self):
        devices: Dict[str, DeviceArgs] = meta.read_devices()
        for device in devices.values():
            if "Eyelink" in device.device_id:
                print(device)
                sensors = meta.read_sensors()
                for sensor_id in device.sensor_ids:
                    device.sensor_array.append(sensors[sensor_id])
                print(device)
                EyeTracker(device)

    def test_create_win(self):
        win = make_win(full_screen=False)
        frame_rate = win.getActualFrameRate()
        print("Frame rate: " + str(frame_rate))