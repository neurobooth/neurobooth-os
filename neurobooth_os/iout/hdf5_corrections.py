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
    desc = get_description(data)
    if 'data_version' in desc.keys():
        return DataVersion.from_str(desc['data_version'][0])
    else:
        return DataVersion(0, 0)


def correct_marker(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.marker_data)
    if data_version.major < 1:
        desc = get_description(data.marker_data)
        desc['data_version'] = [str(data_version)]
        desc['column_names'] = json.dumps(['Marker'])
        desc['column_descriptions'] = json.dumps({'Marker': 'Marker message string'})
    return data


def correct_iphone(data: DeviceData) -> DeviceData:
    data_version = get_data_version(data.device_data)
    print(f'Hey folks, we did it! Data version {data_version}')
    return data