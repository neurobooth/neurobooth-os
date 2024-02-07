from os import environ, path

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, Field, PositiveFloat, PositiveInt
from typing import Optional, List, Callable
import os
import yaml

"""
Loads yaml files containing task/stimulus/instruction parameters and validates them.

To allow variety in the representation of the task parameters, the yaml reading process proceeds in 
two phases. The first phase reads enough to reach the top-level element arg_parser, e.g.:
arg_parser: iout.stim_param_reader.py::EyeTrackerStimArgs()

The arg_parser points to a class that inherits from StimulusArgs (which itself inherits from 
the pydantic BaseModel class). This class handles the parsing of the yaml file in its entirety.

Parsers for all the standard stimulus yaml files are found in this module.   
"""

class SensorArgs(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=255)
    temporal_res: Optional[PositiveFloat] = None
    spatial_res_x: Optional[PositiveFloat] = None
    spatial_res_y: Optional[PositiveFloat] = None
    file_type: str
    arg_parser: str


class FlirSensorArgs(SensorArgs):
    offsetX: PositiveInt
    offsetY: PositiveInt


class EyelinkSensorArgs(SensorArgs):
    calibration_type: str


class DeviceArgs(BaseModel):
    device_id: str
    device_sn: Optional[str] = None
    device_name: str
    device_location: Optional[str] = None
    wearable_bool: bool
    device_make: Optional[str] = None
    device_model: Optional[str] = None
    device_firmware: Optional[str] = None
    sensor_ids: List[str]
    sensor_array: List[SensorArgs] = []
    arg_parser: str


class InstructionArgs(BaseModel):
    """
        Arguments controlling psychopy instructions
    """
    instruction_text: Optional[str] = None
    instruction_filetype: Optional[str] = None
    instruction_file: Optional[str] = None


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
    task_instance: Optional[object] = None  # created by client code from above callable
    device_args: List[DeviceArgs] = []
    class Config:
        arbitrary_types_allowed = True


class EyeTrackerStimArgs(StimulusArgs):
    target_size: NonNegativeFloat = 7


class ClappingStimArgs(EyeTrackerStimArgs):
    text_task: str = Field(min_length=1)


class HeveliusStimArgs(EyeTrackerStimArgs):
    trial_data_fname: str


class HandMovementStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    trial_intruct: List[str]
    countdown: str  # An mp4 filename


class SpeechStimArgs(EyeTrackerStimArgs):
    countdown: str  # An mp4 filename
    text_task: str


class FixationTargetStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    target_pos: List[float]


class PassageReadingStimArgs(EyeTrackerStimArgs):
    countdown: str  # An mp4 filename


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
    start_phase_deg: NonNegativeInt


class CoordPauseStimArgs(EyeTrackerStimArgs):
    end_screen: str
    continue_key: str
    reset_key: str


class CoordPause2StimArgs(EyeTrackerStimArgs):
    slide_image: str
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


def get_cfg_path(folder_name: str) -> str:
    folder = path.join(environ.get("NB_CONFIG"), folder_name)
    return _get_cfg_path(folder)


def _get_cfg_path(folder: str) -> str:
    if not path.exists(folder):
        msg = "Required task configuration folder ('{}') does not exist"
        raise IOError(msg.format(folder))
    return folder


def get_param_dictionary(task_param_file_name: str, folder_name: str) -> dict:
    return _get_param_dictionary(task_param_file_name, get_cfg_path(folder_name))


def _get_param_dictionary(task_param_file_name: str, conf_folder_name: str) -> dict:
    """Returns an unvalidated dictionary containing the attributes from the provided file."""
    filename = os.path.join(conf_folder_name, task_param_file_name)
    if not os.path.exists(filename):
        raise RuntimeError(f"Missing required task configuration file: {filename}.")
    with open(filename) as param_file:
        param_dict = yaml.load(param_file, yaml.FullLoader)
        return param_dict


class RawTaskParams(BaseModel):
    """
        Raw (un-reified) Task params (ie., instead of a list of DeviceArgs,
        it has a list of strings representing device ids
    """

    task_id: str
    feature_of_interest: str
    stimulus_id: str
    instruction_id: Optional[str]
    device_id_array: List[str]
    sensor_id_array: List[List[str]]
