from os import environ, path

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, Field, FilePath
from typing import Optional, List, Callable
import os
import yaml

from neurobooth_os.tasks import Task

"""
Loads a yaml file containing task/stimulus parameters and validates it
"""


class InstructionArgs(BaseModel):
    """
        Arguments controlling psychopy instructions
    """
    instruction_text: Optional[str]
    instruction_filetype: Optional[str]
    instruction_file: Optional[str]


class StimulusArgs(BaseModel):
    """
    Stimulus arguments common to all Psychopy tasks
    """
    stimulus_id: str = Field(min_length=1, max_length=255)
    stimulus_description: str = Field(min_length=1, max_length=255)
    prompt: Optional[bool] = True
    arg_parser: str = Field(min_length=1, max_length=255)
    num_iterations: NonNegativeInt
    duration: Optional[NonNegativeFloat] = None
    stimulus_file_type: str = Field(min_length=1, max_length=255)
    stimulus_file: str = Field(min_length=1, max_length=255)

    task_repeatable_by_subject: Optional[bool] = True

    model_config = ConfigDict(extra='forbid', frozen=True)


class TaskArgs(BaseModel):
    """
    Task function objects and associated arguments
    """
    task_id: str = Field(min_length=1, max_length=255)
    task_constructor_callable: Callable  # callable of constructor for a Task
    stim_args: StimulusArgs
    instr_args: Optional[InstructionArgs] = None
    task_instance: Optional[Task] = None  # created by client code from above callable

    class Config:
        arbitrary_types_allowed = True


class EyeTrackerStimArgs(StimulusArgs):
    target_size: Optional[NonNegativeFloat] = None


class ClappingStimArgs(EyeTrackerStimArgs):
    text_task: str = Field(min_length=1)


class HeveliusStimArgs(EyeTrackerStimArgs):
    trial_data_fname: FilePath


class HandMovementStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    trial_intruct: List[str]
    countdown: FilePath  # An mp4 filename


class SpeechStimArgs(EyeTrackerStimArgs):
    countdown: FilePath  # An mp4 filename
    text_task: str


class FixationTargetStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    target_pos: List[float]


class PassageReadingStimArgs(EyeTrackerStimArgs):
    countdown: FilePath  # An mp4 filename


class SaccadesStimArgs(EyeTrackerStimArgs):
    direction: str
    amplitude_deg: float
    target_size: NonNegativeFloat


class MotStimArgs(EyeTrackerStimArgs):
    time_presentation: NonNegativeInt
    trial_duration: NonNegativeInt
    clickTimeout: NonNegativeInt
    numCircles: NonNegativeInt
    task_repeatable_by_subject: bool


class PursuitStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    peak_velocity_deg: float
    amplitude_deg: float
    starting_offset_deg: float
    ntrials: NonNegativeInt


class CoordPauseStimArgs(EyeTrackerStimArgs):
    end_screen: FilePath
    continue_key: str
    reset_key: str


class CoordPause2StimArgs(EyeTrackerStimArgs):
    slide_image: FilePath
    wait_key: str


class GazeHoldingStimArgs(EyeTrackerStimArgs):
    trial_pos: List[List[float]]
    target_size: NonNegativeFloat


class FingerNoseStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    target_pos: List[float]


class FootTappingStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    trial_intruct: List[str]


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
    if not os.path.exists(filename):
        raise RuntimeError(f"Missing required task configuration file: {filename}.")
    with open(filename) as param_file:
        param_dict = yaml.load(param_file, yaml.FullLoader)
        return param_dict
