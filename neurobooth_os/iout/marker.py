import time
import uuid

from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


def marker_stream(name="Marker", outlet_id=None):
    """Create marker stream to be pushed when needed with a string format:
        "%s_%d_%timestamp" aka code string, number, time

    Parameters
    ----------
    name : str, optional
        marker stream name, by default 'Marker'
    outlet_id : str, optional
        source_id of the stream, by default 'Marker'


    Returns
    -------
    outlet_marker : stream outlet object
        return the stream outlet object created by StreamOutlet
    """

    # Setup outlet stream infos
    if outlet_id is None:
        outlet_id = str(uuid.uuid4())
    stream_info_marker = set_stream_description(
        stream_info=StreamInfo(name, "Markers", 1, channel_format="string", source_id=outlet_id),
        device_id='marker',
        sensor_ids=['marker'],
        data_version=DataVersion(1, 0),
        columns=['Marker'],
        column_desc={'Marker': 'Marker message string'}
    )

    # Create outlets
    outlet_marker = StreamOutlet(stream_info_marker)
    outlet_marker.oulet_id = outlet_id
    outlet_marker.name = name
    outlet_marker.push_sample([f"Stream-created_0_{time.time()}"])
    print(f"-OUTLETID-:{name}:{outlet_id}")
    outlet_marker.stop = outlet_marker.__del__
    outlet_marker.streaming = True

    return outlet_marker
