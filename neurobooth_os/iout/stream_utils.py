import json
from typing import NamedTuple, List, Dict
from pylsl import StreamInfo


class DataVersion(NamedTuple):
    major: int
    minor: int

    def __str__(self):
        return f'{self.major}.{self.minor}'


def set_stream_description(
        stream_info: StreamInfo,
        device_id: str,
        sensor_ids: List[str],
        data_version: DataVersion,
        columns: List[str],
        column_desc: Dict[str, str],
        *,
        contains_chunks: bool = False,
        **additional_descriptors: str,
) -> StreamInfo:
    """
    Sets StreamInfo description elements in a standardized manner.
    This function is to ensure that standard descriptors are present and to reduce the likelihood of typos.

    :param stream_info: The StreamInfo object to set the description for.
    :param device_id: The device ID (e.g., "Mic_Yeti_1")
    :param sensor_ids: A list of sensor IDs (e.g., ["Mic_Yeti_sens_1"])
    :param data_version: The data/file version. Useful for keeping track of evolving data streams and file structures
        (e.g., updated iPhone app versions).
    :param columns: A list of columns included in the data stream.
    :param column_desc: A dictionary of column names and their descriptions.
    :param contains_chunks: Whether this data type contains a large number of columns representing chunks (e.g., audio).
        If True, relaxes the enforcement of column names.
    :param additional_descriptors: Additional keyword arguments with string values will also be added to the stream
        description as-is.
    :returns: The updated StreamInfo object. Not necessary because of side effects, but may help with chaining.
    """
    # Input validation
    if not contains_chunks and (stream_info.channel_count() != len(columns)):
        raise ValueError("Channel count and number of column headers do not match!")
    for c in columns:
        if c not in column_desc:
            raise ValueError(f"No column description supplied for {c}!")

    # Set required descriptions
    stream_info.desc().append_child_value('device_id', device_id)
    stream_info.desc().append_child_value('sensor_ids', json.dumps(sensor_ids))
    stream_info.desc().append_child_value('data_version', str(data_version))
    stream_info.desc().append_child_value('column_names', json.dumps(columns))
    stream_info.desc().append_child_value('column_descriptions', json.dumps(column_desc))

    # Set additional descriptions if present
    for desc, val in additional_descriptors.items():
        stream_info.desc().append_child_value(desc, val)

    return stream_info
