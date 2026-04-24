import time
import uuid
from typing import Any, List, Mapping, Optional

from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.device import Device, DeviceCapability, DeviceState
from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.msg.messages import DeviceInitialization, Request
import neurobooth_os.iout.metadator as meta


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
    outlet_marker.outlet_id = outlet_id
    outlet_marker.name = name
    outlet_marker.push_sample([f"Stream-created_0_{time.time()}"])

    msg_body = DeviceInitialization(stream_name=name, outlet_id=outlet_id)
    message = Request(source="marker", destination='CTR', body=msg_body)
    meta.post_message(message)

    outlet_marker.stop = outlet_marker.__del__
    outlet_marker.streaming = True

    return outlet_marker


class MarkerStreamDevice(Device):
    """Device wrapper around the LSL marker outlet.

    The marker outlet has no hardware — it exists to let tasks annotate the
    data stream. Wrapping it in a ``Device`` lets ``DeviceManager`` treat it
    like any other config-driven stream.

    Tasks call ``push_sample()`` directly on this object via the
    ``marker_outlet`` that ``STMSession`` forwards from ``DeviceManager.streams``.
    """

    capabilities = DeviceCapability.STREAM

    _DEFAULT_DEVICE_ID = "marker"

    def __init__(self, device_args: Optional[DeviceArgs] = None,
                 name: str = "Marker") -> None:
        super().__init__(device_args)
        if self.device_id is None:
            self.device_id = self._DEFAULT_DEVICE_ID
            self.sensor_ids = [self._DEFAULT_DEVICE_ID]
        self.name = name

    def connect(self) -> None:
        stream_info = set_stream_description(
            stream_info=StreamInfo(
                self.name, "Markers", 1, channel_format="string", source_id=self.outlet_id
            ),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['Marker'],
            column_desc={'Marker': 'Marker message string'},
        )
        self.outlet = StreamOutlet(stream_info)
        self.outlet.push_sample([f"Stream-created_0_{time.time()}"])

        body = DeviceInitialization(stream_name=self.name, outlet_id=self.outlet_id)
        meta.post_message(Request(source="marker", destination='CTR', body=body))
        self.state = DeviceState.CONNECTED

    def start(self, filename: Optional[str] = None) -> List[str]:
        self.streaming = True
        self.state = DeviceState.STARTED
        return []

    def stop(self) -> None:
        self.streaming = False
        self.state = DeviceState.STOPPED
        if self.outlet is not None:
            self.outlet.__del__()
            self.outlet = None

    def push_sample(self, sample: List[Any]) -> None:
        """Forward a marker sample to the underlying LSL outlet."""
        self.outlet.push_sample(sample)
