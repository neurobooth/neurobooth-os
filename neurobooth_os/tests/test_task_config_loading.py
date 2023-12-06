import unittest
from os import environ, path
from pydantic import BaseModel
from neurobooth_os.tasks.task import Task

from neurobooth_os.iout.ParameterConfigReader import _get_cfg_path, _get_param_dictionary


class TestTask(BaseModel):
    stimulus_description: str


class TestTaskParamReader(unittest.TestCase):
    pass

    def test_read_success(self):
        folder = path.join(environ.get("NB_CONFIG"), "tasks")
        config_path = _get_cfg_path(folder)
        self.assertTrue(isinstance(config_path, str))
        self.assertIsNotNone(config_path)

    def test_io_error(self):
        folder = "wrwqtwwefsdfasq"
        self.assertRaises(IOError, _get_cfg_path, folder)

    def test_parse_file(self):
        folder = path.join(environ.get("NB_CONFIG"), "tasks")
        param_dict = _get_param_dictionary("calibrate.yml", folder)
        self.assertIsNotNone(param_dict)

    def test_validate_task(self):
        folder = path.join(environ.get("NB_CONFIG"), "tasks")
        param_dict = _get_param_dictionary("calibrate.yml", folder)
        test_task = TestTask(**param_dict)
        self.assertIsNotNone(test_task)

    def test_junk(self):
        t = Task()
        print(t)

    def test_junk2(self):
        class TaskJunk:
            def __init__(
                    self,
                    temp="nothing",
                    **kwargs
            ):
                self.temp = temp
            pass

        vars2 = {
            "temp": "something",
            "temp2": 4
        }
        t = TaskJunk(**vars2)
        print(t.temp)

