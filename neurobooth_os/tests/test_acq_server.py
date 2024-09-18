import unittest
from typing import List

from neurobooth_os.iout.lsl_streamer import DeviceManager
from neurobooth_os.iout.stim_param_reader import DeviceArgs
import neurobooth_os.iout.metadator as meta


class TestTaskParamReader(unittest.TestCase):

    def test_is_camera(self):
        d = DeviceManager("acquisition")
        self.assertTrue(d.is_camera("FLIR_blackfly_1"))

    def test_get_camera_streams(self):
        d = DeviceManager("acquisition")
        device_args: List[DeviceArgs] = list(meta.read_devices().values())
        print(device_args)
        device_ids = [dev.device_id for dev in device_args]
        print(device_ids)
        camera_streams = d.get_camera_streams(device_args)
        print(camera_streams)

    def test_get_dev_kwargs(self):
        collection_id = 'testing'
        task_params = meta.build_tasks_for_collection(collection_id)
        devkwargs = DeviceManager._get_unique_devices(task_params)
        print(devkwargs)

    def test_start_flir(self):
        d = DeviceManager("acquisition")
        fname = "foo"
        devices = list(meta.read_devices().values())
        d.start_cameras(filename=fname, task_devices=devices)