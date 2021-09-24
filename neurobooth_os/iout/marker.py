import time
import uuid

from pylsl import StreamInfo, StreamOutlet


def marker_stream(name='Marker'):
    """Create marker stream to be pushed when needed with a string format:
        "%s_%d_%timestamp" aka code string, number, time

    Parameters
    ----------
    name : str, optional
        marker stream name, by default 'Marker'

    Returns
    -------
    outlet_marker : stream outlet object
        return the stream outlet object created by StreamOutlet
    """


    # Setup outlet stream infos
    oulet_id = str(uuid.uuid4())
    stream_info_marker = StreamInfo(name, 'Markers', 1,
                                    channel_format='string', source_id=oulet_id)

    # Create outlets
    outlet_marker = StreamOutlet(stream_info_marker)
    outlet_marker.oulet_id = oulet_id
    outlet_marker.push_sample([f"Stream-created_0_{time.time()}"])
    print(f"-OUTLETID-:Marker:{oulet_id}")
    outlet_marker.stop = outlet_marker.__del__
    outlet_marker.streaming = True

    return outlet_marker
