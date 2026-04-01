import logging
from typing import Optional

from pynput import mouse
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.device import Device, DeviceCapability, DeviceState
from neurobooth_os.iout.metadator import post_message
from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os.msg.messages import DeviceInitialization, Request


class MouseStream(Device):

    capabilities = DeviceCapability.STREAM

    def __init__(self, device_args: DeviceArgs) -> None:
        super().__init__(device_args)
        self._device_args = device_args

    def connect(self) -> None:
        """Create the LSL outlet and notify the control server."""
        self._info_stream = set_stream_description(
            stream_info=StreamInfo(
                name="Mouse",
                type="mouse",
                channel_count=3,
                channel_format="int32",
                source_id=self.outlet_id,
            ),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['PosX', 'PosY', 'MouseState'],
            column_desc={
                'PosX': 'X screen coordinate of the mouse (pixels)',
                'PosY': 'y screen coordinate of the mouse (pixels)',
                'MouseState': 'Flag for the state of the mouse (0=move, 1=click, -1=release)',
            }
        )
        self.outlet = StreamOutlet(self._info_stream)
        body = DeviceInitialization(
            stream_name='Mouse',
            outlet_id=self.outlet_id,
            device_id=self.device_id,
        )
        msg = Request(source="MouseStream", destination="CTR", body=body)
        post_message(msg)
        self.state = DeviceState.CONNECTED
        self.logger.debug('Mouse: Created Object')

    def start(self, filename: Optional[str] = None) -> None:
        """Begin listening to mouse events."""
        self.streaming = True
        self.state = DeviceState.STARTED
        self._create_listener()
        self.logger.debug('Mouse: Starting Listener')
        self.listener.start()

        try:
            self.outlet.push_sample([0, 0, 0])
        except BaseException:  # "OSError" from C++
            self.logger.debug("Mouse stream already closed, reopening")
            self.outlet = StreamOutlet(self._info_stream)

    def _create_listener(self) -> None:
        """Set up the pynput mouse listener with callbacks."""
        def on_move(x, y):
            mysample = [x, y, 0]
            try:
                self.outlet.push_sample(mysample)
            except BaseException:
                self.logger.debug("Mouse listener caught error pushing outlet, mouse move")

        def on_click(x, y, button, pressed):
            state = 1 if pressed else -1
            mysample = [x, y, state]
            try:
                self.outlet.push_sample(mysample)
            except BaseException:
                self.logger.debug("Mouse listener caught error pushing outlet, click")

        self.listener = mouse.Listener(on_move=on_move, on_click=on_click)

    def stop(self) -> None:
        """Stop listening to mouse events."""
        if self.streaming:
            self.streaming = False
            self.state = DeviceState.STOPPED
            self.listener.stop()
            self.logger.debug('Mouse: Stopped Listener')
