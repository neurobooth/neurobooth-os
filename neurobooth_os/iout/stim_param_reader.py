from os import environ, path

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, Field, PositiveFloat, PositiveInt
from typing import Optional, List, Callable, Tuple
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


class StudyArgs(BaseModel):
    study_id: str = Field(min_length=1, max_length=255)
    study_title: str = Field(min_length=1, max_length=512)
    collection_ids: List[str]
    irb_protocol_number: Optional[NonNegativeInt] = None
    protocol_version: Optional[NonNegativeInt] = None
    arg_parser: str


class CollectionArgs(BaseModel):
    collection_id: str = Field(min_length=1, max_length=255)
    is_active: bool
    task_ids: List[str]
    arg_parser: str


class SensorArgs(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=255)
    file_type: str
    arg_parser: str


class StandardSensorArgs(SensorArgs):
    temporal_res: Optional[PositiveFloat] = None
    spatial_res_x: Optional[PositiveFloat] = None
    spatial_res_y: Optional[PositiveFloat] = None


class MbientSensorArgs(SensorArgs):
    hz: PositiveFloat


class IntelSensorArgs(SensorArgs):
    fps: PositiveInt
    size_x: PositiveInt
    size_y: PositiveInt
    size: Optional[Tuple[float, float]] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (self.size_x, self.size_y)


class FlirSensorArgs(StandardSensorArgs):
    offsetX: PositiveInt
    offsetY: PositiveInt


class MicYetiSensorArgs(SensorArgs):
    RATE: PositiveInt
    CHUNK: PositiveInt


class EyelinkSensorArgs(StandardSensorArgs):
    calibration_type: str
    sample_rate: PositiveInt


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


class MicYetiDeviceArgs(DeviceArgs):
    microphone_name: str
    sensor_array: List[MicYetiSensorArgs] = []


class EyelinkDeviceArgs(DeviceArgs):
    """
    Eyelink device arguments
    The eyelink should only one sensor, represented by an instance
    of type EyelinkSensorArgs
    """
    ip: Optional[str] = None
    sensor_array: List[EyelinkSensorArgs] = []

    def sample_rate(self):
        return self.sensor_array[0].sample_rate

    def calibration_type(self):
        return self.sensor_array[0].calibration_type


class FlirDeviceArgs(DeviceArgs):
    """
    FLIR device arguments
    The FLIR should only one sensor, represented by an instance
    of type FlirSensorArgs
    """
    sensor_array: List[FlirSensorArgs] = []

    def fps(self):
        return self.sensor_array[0].fps

    def sizex(self):
        return self.sensor_array[0].sizex

    def sizey(self):
        return self.sensor_array[0].sizey


class IntelDeviceArgs(DeviceArgs):
    sensor_array: List[IntelSensorArgs] = []

    def fps(self):
        """
        Returns a tuple containing the fps value from each sensor

        Returns
        -------
        tuple(float, float)
        """
        fps_rgb = None
        fps_depth = None
        for sensor in self.sensor_array:
            if 'depth' in sensor.sensor_id:
                fps_depth = sensor.fps
            elif 'rgb' in sensor.sensor_id:
                fps_rgb = sensor.fps
        result = (fps_rgb, fps_depth)
        return result

    def framesize(self):
        """
        Returns a tuple containing the fps value from each sensor

        Returns
        -------
        tuple(float, float)
        """
        framesize_rgb = None
        framesize_depth = None
        for sensor in self.sensor_array:
            if 'depth' in sensor.sensor_id:
                framesize_depth = sensor.size
            elif 'rgb' in sensor.sensor_id:
                framesize_rgb = sensor.size
        result = (framesize_rgb, framesize_depth)
        return result

    def has_depth_sensor(self):
        for sensor in self.sensor_array:
            if 'depth' in sensor.sensor_id:
                return True
        return False


class MbientDeviceArgs(DeviceArgs):
    sensor_array: List[MbientSensorArgs] = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_name = self.device_id.split("_")[1]


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

    # task_instance is a Task, but using Optional[Task] as the type causes circular import problems
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
    trial_intruct: List[str]


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
