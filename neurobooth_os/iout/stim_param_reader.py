from os import environ, path

from pydantic import BaseModel, ConfigDict, NonNegativeFloat, NonNegativeInt, Field, PositiveInt, PositiveFloat, \
    SerializeAsAny
from typing import Optional, List, Callable, Tuple, Dict
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


class EnvArgs(BaseModel):
    """
    Standard superclass for any param type that might include environment-specific variables.
    These variables can and should be ignored where they're not needed.
    """
    ENV_devices: Optional[Dict]


class StudyArgs(EnvArgs):
    study_id: str = Field(min_length=1, max_length=255)
    study_title: str = Field(min_length=1, max_length=512)
    collection_ids: List[str]
    irb_protocol_number: Optional[NonNegativeInt] = None
    protocol_version: Optional[NonNegativeInt] = None
    arg_parser: str


class CollectionArgs(EnvArgs):
    collection_id: str = Field(min_length=1, max_length=255)
    is_active: bool
    session_start_slide: str
    session_end_slide: str
    task_ids: List[str]
    arg_parser: str


class SensorArgs(EnvArgs):

    # Attributes required for program execution
    sensor_id: str = Field(min_length=1, max_length=255)
    arg_parser: str

    # Attributes used for logging and documentation only
    file_type: Optional[str]


class StandardSensorArgs(SensorArgs):

    # Attributes used as device parameters
    sample_rate: PositiveInt
    width_px: PositiveInt
    height_px: PositiveInt


class MbientSensorArgs(SensorArgs):

    # Attributes used as device parameters
    sample_rate: PositiveInt
    data_range: PositiveInt


class IntelSensorArgs(StandardSensorArgs):
    size: Optional[Tuple[float, float]] = None

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.size = (self.width_px, self.height_px)


class FlirSensorArgs(StandardSensorArgs):

    # Attributes used as device parameters
    offsetX: PositiveInt
    offsetY: PositiveInt
    exposure: PositiveInt
    gain: PositiveInt
    gamma: PositiveFloat
    fd: PositiveInt


class MicYetiSensorArgs(SensorArgs):

    # Attributes used as device parameters
    sample_rate: PositiveInt
    sample_chunk_size: PositiveInt
    input: bool
    output: bool
    channels: PositiveInt
    format: str


class EyelinkSensorArgs(SensorArgs):

    # Attributes used as device parameters
    sample_rate: PositiveInt
    calibration_type: str
    msec_delay: NonNegativeInt
    calibration_area_proportion: Tuple[float, float]
    validation_area_proportion: Tuple[float, float]


class IPhoneSensorArgs(SensorArgs):

    # Attributes used as device parameters
    sample_rate: PositiveInt
    notifyonframe: PositiveInt
    videoquality: str
    usecamerafacing: str
    brightness: PositiveInt
    lenspos: float


class DeviceArgs(EnvArgs):
    ENV_devices: Dict           # Environment-specific device arguments

    # Attributes required for program execution
    device_id: str                                  # Unique identifier for device
    device_start_function: str      # A string representing the function that starts the device
    arg_parser: str                 # A string representing the function that parses the device arguments into objects
    sensor_ids: Optional[List[str]]                 # List of unique identifiers for sensors contained in device
    sensor_array: List[SerializeAsAny[SensorArgs]] = []     # List of the SensorArgs for sensors in device

    # Device parameter (where used)
    device_sn: Optional[str] = None     # Serial number for individual device

    # Attributes used for logging and documentation only
    device_name: Optional[str] = None   # Descriptive string for device type
    wearable_bool: Optional[bool] = None    # True if the device is wearable; false otherwise

    # Attributes used for documentation only (Not logged)
    device_make: Optional[str] = None   # Manufacturer name
    device_model: Optional[str] = None  # Model name
    device_firmware: Optional[str] = None   # Firmware version

    def __init__(self, **kwargs):
        # pull-in environment specific parameter "device_sn", updating the kwargs with the appropriate value
        my_id = kwargs.get('device_id')
        if my_id in kwargs['ENV_devices']:
            my_dict = kwargs['ENV_devices'][my_id]
            if 'device_sn' in my_dict:
                sn = my_dict['device_sn']
                kwargs['device_sn'] = sn
        super().__init__(**kwargs)


class MicYetiDeviceArgs(DeviceArgs):

    # Attributes required for program execution
    microphone_name: str
    sensor_array: List[MicYetiSensorArgs] = []

    def __init__(self, **kwargs):

        # pull-in environment specific parameter "microphone_name", updating the kwargs with the appropriate value
        my_id = kwargs.get('device_id')
        mic_nm = kwargs['ENV_devices'][my_id]['microphone_name']
        kwargs['microphone_name'] = mic_nm
        super().__init__(**kwargs)


class EyelinkDeviceArgs(DeviceArgs):
    """
    Eyelink device arguments
    The eyelink should have only one sensor, represented by an instance
    of type EyelinkSensorArgs
    """

    # Attributes required for program execution
    ip: str
    sensor_array: List[EyelinkSensorArgs] = []

    def __init__(self, **kwargs):
        # pull-in environment specific parameter "ip", updating the kwargs with the appropriate value
        my_id = kwargs.get('device_id')
        ip_addr = kwargs['ENV_devices'][my_id]['ip']
        kwargs['ip'] = ip_addr

        super().__init__(**kwargs)

    def msec_delay(self):
        return self.sensor_array[0].msec_delay

    def calibration_area_proportion(self):
        return self.sensor_array[0].calibration_area_proportion

    def validation_area_proportion(self):
        return self.sensor_array[0].validation_area_proportion

    def sample_rate(self):
        return self.sensor_array[0].sample_rate

    def calibration_type(self):
        return self.sensor_array[0].calibration_type


class IPhoneDeviceArgs(DeviceArgs):
    """
    IPhone device arguments
    The IPhone should have only one sensor, represented by an instance
    of type IPhoneSensorArgs

    """
    # Attributes required for program execution
    sensor_array: List[IPhoneSensorArgs] = []

    def sample_rate(self):
        return str(self.sensor_array[0].sample_rate)

    def notifyonframe(self):
        return str(self.sensor_array[0].notifyonframe)

    def videoquality(self):
        return self.sensor_array[0].videoquality

    def usecamerafacing(self):
        return self.sensor_array[0].usecamerafacing

    def brightness(self):
        return str(self.sensor_array[0].brightness)

    def lenspos(self):
        return str(self.sensor_array[0].lenspos)


class FlirDeviceArgs(DeviceArgs):
    """
    FLIR device arguments
    The FLIR should have only one sensor, represented by an instance
    of type FlirSensorArgs
    """

    # Attributes required for program execution
    sensor_array: List[FlirSensorArgs] = []

    def __init__(self, **kwargs):
        # pull-in environment specific param "device_sn", updating the kwargs with the appropriate value
        my_id = kwargs.get('device_id')
        sn = kwargs['ENV_devices'][my_id]['device_sn']
        kwargs['device_sn'] = sn
        super().__init__(**kwargs)

    def exposure(self) -> PositiveInt:
        return self.sensor_array[0].exposure

    def gain(self) -> PositiveInt:
        return self.sensor_array[0].gain

    def gamma(self) -> PositiveFloat:
        return self.sensor_array[0].gamma

    def fd(self) -> PositiveInt:
        return self.sensor_array[0].fd

    def sample_rate(self):
        return self.sensor_array[0].sample_rate

    def width_px(self):
        return self.sensor_array[0].width_px

    def height_px(self):
        return self.sensor_array[0].height_px

    def offset_x(self):
        return self.sensor_array[0].offsetX

    def offset_y(self):
        return self.sensor_array[0].offsetY


class IntelDeviceArgs(DeviceArgs):

    # Attributes required for program execution
    sensor_array: List[IntelSensorArgs] = []
    auto_exposure_priority: NonNegativeFloat

    def sample_rate(self):
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
                fps_depth = sensor.sample_rate
            elif 'rgb' in sensor.sensor_id:
                fps_rgb = sensor.sample_rate
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


class WebcamDeviceArgs(DeviceArgs):
    """
    Webcam device arguments
    The webcam should be only one sensor, represented by an instance of type StandardSensorArgs
    """

    # Attributes required for program execution
    camera_idx: int
    fourcc: str  # Video codec to use
    n_frames_to_flush: int  # Number of frames to discard before recording
    sensor_array: List[StandardSensorArgs] = []

    def __init__(self, **kwargs):
        # pull-in environment specific param "camera_idx", updating the kwargs with the appropriate value
        my_id = kwargs.get('device_id')
        camera_idx = kwargs['ENV_devices'][my_id]['camera_idx']
        kwargs['camera_idx'] = camera_idx
        super().__init__(**kwargs)

    def sample_rate(self):
        return self.sensor_array[0].sample_rate

    def width_px(self):
        return self.sensor_array[0].width_px

    def height_px(self):
        return self.sensor_array[0].height_px


class MbientDeviceArgs(DeviceArgs):

    # Attributes required for program execution
    sensor_array: List[MbientSensorArgs] = []
    mac: str

    def __init__(self, **kwargs):
        # pull-in environment specific param "mac", updating the kwargs with the appropriate value
        my_id = kwargs.get('device_id')
        mac_1 = kwargs['ENV_devices'][my_id]['mac']
        kwargs['mac'] = mac_1

        super().__init__(**kwargs)
        self.device_name = self.device_id.split("_")[1]


class InstructionArgs(EnvArgs):
    """
        Arguments controlling psychopy instructions
    """
    instruction_text: Optional[str] = None
    instruction_filetype: Optional[str] = None
    instruction_file: Optional[str] = None

    start_task_slide: str = 'inst_end_task_disabled.png'
    start_task_repeat_instr_slide: str = 'inst_end_task.png'


class StimulusArgs(EnvArgs):
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
    record_data: Optional[bool] = True     # should data from the task be recorded
    model_config = ConfigDict(extra='forbid', frozen=True)


class TaskArgs(BaseModel):
    """
    Task function objects and associated arguments
    """
    task_id: str = Field(min_length=1, max_length=255)
    task_constructor_callable: Callable  # callable of constructor for a Task
    stim_args: SerializeAsAny[StimulusArgs]
    instr_args: Optional[SerializeAsAny[InstructionArgs]] = None
    feature_of_interest: str

    # task_instance is a Task, but using Optional[Task] as the type causes circular import problems
    task_instance: Optional[object] = None  # created by client code from above callable
    device_args: List[SerializeAsAny[DeviceArgs]] = []
    arg_parser: str

    class Config:
        arbitrary_types_allowed = True

    def dump_filtered(self) -> dict:
        """

        Returns a dictionary containing the components of this model.  All entries containing None are excluded, and
        a number of items not essential for documenting the session are also excluded
        -------

        """

        key_list = ['task_instance', 'arg_parser', 'sensor_ids']
        dictionary = self.model_dump(exclude_none=True)

        def delete_keys_from_dict(dict_del, lst_keys):
            dict_keys = list(dict_del.keys())  # Used as iterator to avoid the 'DictionaryHasChanged' error
            for key in dict_keys:
                if key in lst_keys:
                    del dict_del[key]
                elif key in dict_del and type(dict_del[key]) == dict:
                    delete_keys_from_dict(dict_del[key], lst_keys)
                elif key in dict_del and type(dict_del[key]) == list:
                    for item in dict_del[key]:
                        delete_keys_from_dict(item, key_list)

        delete_keys_from_dict(dictionary, key_list)

        return dictionary


class EyeTrackerStimArgs(StimulusArgs):
    target_size: NonNegativeFloat = 7


class ProgressBarStimArgs(StimulusArgs):
    slide_image: str
    wait_keys: bool = False


class BreakVideoStimArgs(StimulusArgs):
    video_file: str
    wait_keys: bool = False


class StanceStimArgs(StimulusArgs):
    trial_intruct: List[str]
    wait_keys: bool
    trial_text: str = 'Press CONTINUE to end trial'
    screen_update_interval: Optional[int] = None
    countdown: Optional[str] = None # An mp4 filename


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


class CountingStimArgs(StimulusArgs):
    text_task: str


class FixationTargetStimArgs(EyeTrackerStimArgs):
    target_size: NonNegativeFloat
    target_pos: List[float]


class PassageReadingStimArgs(EyeTrackerStimArgs):
    countdown: str  # An mp4 filename
    image_to_render_on_tablet: str
    image_to_render_on_HostPC: str

class SaccadesStimArgs(EyeTrackerStimArgs):
    direction: str
    amplitude_deg: float
    target_size: NonNegativeFloat


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


class TimingTestStimArgs(EyeTrackerStimArgs):
    monochrome: bool
    tone_freq: NonNegativeInt
    tone_duration: NonNegativeFloat
    wait_center: NonNegativeFloat
    num_iterations: NonNegativeInt


class SdmtStimArgs(EyeTrackerStimArgs):
    duration: PositiveFloat
    symbols: List[str]
    seed: Optional[int]
    text_font: str
    text_height: PositiveFloat
    continue_text_height: PositiveFloat
    cell_size: PositiveFloat
    interline_gap: NonNegativeFloat
    grid_rows: PositiveInt
    grid_cols: PositiveInt
    practice_grid_rows: PositiveInt
    practice_grid_cols: PositiveInt
    mouse_visible: bool


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


class RawTaskParams(EnvArgs):
    """
        Raw (un-reified) Task params (i.e., instead of a list of DeviceArgs,
        it has a list of strings representing device ids
    """

    task_id: str
    feature_of_interest: str
    stimulus_id: str
    instruction_id: Optional[str] = None
    device_id_array: List[str]
    arg_parser: str
