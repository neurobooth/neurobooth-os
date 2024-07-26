"""
HDF5 correction functions are implemented in this file to avoid dependency nightmares.
It is also possible to implement them in the device files, or as separate supplements to device files.
"""

import json
from neurobooth_os.iout.split_xdf import DeviceData
from neurobooth_os.iout.stream_utils import DataVersion


def get_description(data):
    """Helper function to retrieve the description element of the XDF structure."""
    return data['info']['desc'][0]


def get_data_version(data) -> DataVersion:
    """Extract the data version from the device or marker data. Assume v0.0 if the key is missing."""
    try:
        desc = get_description(data)
        return DataVersion.from_str(desc['data_version'][0])
    except (KeyError, AttributeError):  # Old marker descriptions don't have the full structure or store data version
        return DataVersion(0, 0)


def correct_marker(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        data.marker_data['info']['desc'] = {
            'data_version': [str(data_version)],
            'column_names': json.dumps(['Marker']),
            'column_descriptions': json.dumps({'Marker': 'Marker message string'}),
            'device_id': 'marker',
            'sensor_ids': json.dumps(['marker']),
        }
    return data


def correct_intel(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['FrameNum', 'FrameNum_RealSense', 'Time_RealSense', 'Time_ACQ'])
        desc['column_descriptions'] = json.dumps({
            'FrameNum': 'Locally-tracked frame number',
            'FrameNum_RealSense': 'Camera-tracked frame number',
            'Time_RealSense': 'Camera timestamp (ms)',
            'Time_ACQ': 'Local machine timestamp (s)',
        })
    return data


def correct_eyelink(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps([
            'R_GazeX', 'R_GazeY', 'R_PupilSize',
            'L_GazeX', 'L_GazeY', 'L_PupilSize',
            'Target_PositionX', 'Target_PositionY', 'Target_Distance',
            'R_PPD', 'L_PPD',
            'Time_EDF', 'Time_NUC'
        ])
        desc['column_descriptions'] = json.dumps({
            'R_GazeX': 'Right eye: Horizontal gaze location on screen (pixels)',
            'R_GazeY': 'Right eye: Vertical gaze location on screen (pixels)',
            'R_PupilSize': 'Right eye: Pupil size (arbitrary units; see EyeLink documentation)',
            'L_GazeX': 'Left eye: Horizontal gaze location on screen (pixels)',
            'L_GazeY': 'Left eye: Vertical gaze location on screen (pixels)',
            'L_PupilSize': 'Left eye: Pupil size (arbitrary units; see EyeLink documentation)',
            'Target_PositionX': 'Horizontal location of the bullseye target (camera pixels)',
            'Target_PositionY': 'Vertical location of the bullseye target (camera pixels)',
            'Target_Distance': 'Distance to the bullseye target',
            'R_PPD': 'Right eye: Angular resolution at current gaze position (pixels per visual degree)',
            'L_PPD': 'Left eye: Angular resolution at current gaze position (pixels per visual degree)',
            'Time_EDF': 'Timestamp within the EDF file (ms)',
            'Time_NUC': 'Local timestamp of sample receipt by the NUC machine (s)',
        })
    return data


def correct_flir(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['FrameNum', 'Time_FLIR'])
        desc['column_descriptions'] = json.dumps({
            'FrameNum': 'Frame number',
            'Time_FLIR': 'Camera timestamp (ns)',
        })
    return data


def correct_iphone(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.device_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['FrameNum', 'Time_iPhone', 'Time_ACQ'])
        desc['column_descriptions'] = json.dumps({
            'FrameNum': 'App-tracked frame number',
            'Time_iPhone': 'App timestamp (s)',
            'Time_ACQ': 'Local machine timestamp (s)',
        })
    return data


def correct_mbient(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['Time_Mbient', 'AccelX', 'AccelY', 'AccelZ', 'GyroX', 'GyroY', 'GyroZ'])
        desc['column_descriptions'] = json.dumps({
            'Time_Mbient': 'Device timestamp (ms; epoch)',
            'AccelX': 'X component of acceleration in local coordinate frame (g)',
            'AccelY': 'Y component of acceleration in local coordinate frame (g)',
            'AccelZ': 'Z component of acceleration in local coordinate frame (g)',
            'GyroX': 'Angular velocity about X axis in local coordinate frame (deg/s)',
            'GyroY': 'Angular velocity about Y axis in local coordinate frame (deg/s)',
            'GyroZ': 'Angular velocity about Z axis in local coordinate frame (deg/s)',
        })
    return data


def correct_yeti(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.device_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['ElapsedTime', 'Amplitude (1024 samples)'])
        desc['column_descriptions'] = json.dumps({
            'ElapsedTime': 'Elapsed time on the local LSL clock since the last chunk of samples (ms)',
            'Amplitude (1024 samples)': 'Remaining columns represent a chunk of audio samples.',
        })
    return data


def correct_mouse(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.device_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['PosX', 'PosY', 'MouseState'])
        desc['column_descriptions'] = json.dumps({
            'PosX': 'X screen coordinate of the mouse (pixels)',
            'PosY': 'y screen coordinate of the mouse (pixels)',
            'MouseState': 'Flag for the state of the mouse (0=move, 1=click, -1=release)',
        })
    return data
