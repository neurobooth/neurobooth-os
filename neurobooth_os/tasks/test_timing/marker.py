from pylsl import StreamInfo, StreamOutlet
import time
import uuid

from neurobooth_os.msg.messages import DeviceInitialization, Request
import neurobooth_os.iout.metadator as meta

def marker_stream():
    """Create marker stream to be pushed when needed with a string format:
    "%s_%d_%timestamp" aka code string, number, time"""

    # Setup outlet stream infos
    oulet_id = str(uuid.uuid4())
    stream_info_marker = StreamInfo(
        "Marker", "Markers", 1, channel_format="string", source_id=oulet_id
    )

    # Create outlets
    outlet_marker = StreamOutlet(stream_info_marker)
    outlet_marker.oulet_id = oulet_id
    outlet_marker.push_sample([f"Stream-created_0_{time.time()}"])
    msg_body = DeviceInitialization(stream_name="Marker", outlet_id=oulet_id)
    message = Request(source="marker", destination='CTR', body=msg_body)
    with meta.get_database_connection() as conn:
        meta.post_message(message, conn)

    outlet_marker.stop = outlet_marker.__del__
    outlet_marker.streaming = True

    return outlet_marker
