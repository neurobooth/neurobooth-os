from os import environ, path
import os
import yaml
from pydantic import BaseModel

"""
Loads a yaml file containing task/stimulus parameters and validates it
"""


def get_cfg_path() -> str:
    folder = path.join(environ.get("NB_CONFIG"), "tasks")
    return _get_cfg_path(folder)


def _get_cfg_path(folder: str) -> str:
    if not path.exists(folder):
        msg = "Required task configuration folder ('{}') does not exist"
        raise IOError(msg.format(folder))
    return folder


def get_param_dictionary(task_param_file_name: str) -> dict:
    return _get_param_dictionary(task_param_file_name, get_cfg_path())


def _get_param_dictionary(task_param_file_name: str, conf_folder_name: str) -> dict:
    filename = os.path.join(conf_folder_name, task_param_file_name)
    with open(filename) as param_file:
        return yaml.load(param_file, yaml.FullLoader)
