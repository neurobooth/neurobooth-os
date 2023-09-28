"""
Device-specific functions for correcting old data files.
Most of this file should be refactored when devices are made more extensible.
Device configs will need to be able to specify an optional hook to register these functions from the device code.
"""

import json
from typing import Dict, Callable
from neurobooth_os.iout.stream_utils import DataVersion
from neurobooth_os.iout.split_xdf import DeviceData


def get_description(data):
    """Helper function to retrieve the description element of the XDF structure."""
    return data['info']['desc'][0]


def get_data_version(data) -> DataVersion:
    """Extract the data version from the device or marker data. Assume v0.0 if the key is missing."""
    desc = get_description(data)
    if 'data_version' in desc.keys():
        return DataVersion.from_str(desc['data_version'][0])
    else:
        return DataVersion(0, 0)


def correct_marker(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        desc = get_description(data)
        desc['data_version'] = str(data_version)
        desc['column_names'] = json.dumps(['Marker'])
        desc['column_descriptions'] = json.dumps({'Marker': 'Marker message string'})
    return data


def _correct_iphone(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.device_data)
    return data


HDF5_CORRECT_HOOKS: Dict[str, Callable[[DeviceData], DeviceData]] = {
    'Eyelink_1': lambda x: x,
    'FLIR_blackfly_1': lambda x: x,
    'Intel_D455_1': lambda x: x,
    'Intel_D455_2': lambda x: x,
    'Intel_D455_3': lambda x: x,
    'IPhone_dev_1': _correct_iphone,
    'Mbient_BK_1': lambda x: x,
    'Mbient_LF_1': lambda x: x,
    'Mbient_LF_2': lambda x: x,
    'Mbient_LH_1': lambda x: x,
    'Mbient_LH_2': lambda x: x,
    'Mbient_RF_2': lambda x: x,
    'Mbient_RH_1': lambda x: x,
    'Mbient_RH_2': lambda x: x,
    'Mic_Yeti_dev_1': lambda x: x,
    'Mouse': lambda x: x,
}
