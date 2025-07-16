import uuid
import logging

from pynput import mouse
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.metadator import get_database_connection, post_message
from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os.msg.messages import DeviceInitialization, Request


class MouseStream:
    def __init__(self, device_args: DeviceArgs):

        self.oulet_id = str(uuid.uuid4())
        self.info_stream = set_stream_description(
            stream_info=StreamInfo(
                name="Mouse",
                type="mouse",
                channel_count=3,
                channel_format="int32",
                source_id=self.oulet_id,
            ),
            device_id=device_args.device_id,
            sensor_ids=device_args.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['PosX', 'PosY', 'MouseState'],
            column_desc={
                'PosX': 'X screen coordinate of the mouse (pixels)',
                'PosY': 'y screen coordinate of the mouse (pixels)',
                'MouseState': 'Flag for the state of the mouse (0=move, 1=click, -1=release)',
            }
        )
        self.outlet = StreamOutlet(self.info_stream)
        body = DeviceInitialization(
            stream_name='Mouse',
            outlet_id=self.oulet_id,
            device_id=device_args.device_id,
        )
        msg = Request(source="MouseStream", destination="CTR", body=body)
        with get_database_connection() as conn:
            post_message(msg, conn)

        self.streaming = False

        self.logger = logging.getLogger(APP_LOG_NAME)
        self.logger.debug('Mouse: Created Object')

    def start(self):
        self.streaming = True
        self.stream()
        self.logger.debug('Mouse: Starting Listener')
        self.listener.start()

        try:
            self.outlet.push_sample([0, 0, 0])
        except BaseException:  # "OSError" from C++
            self.logger.debug("Mouse stream already closed, reopening")
            self.outlet = StreamOutlet(self.info_stream)

    def stream(self):
        def on_move(x, y):
            mysample = [x, y, 0]
            try:
                self.outlet.push_sample(mysample)  # , timestamp=time.time())
            except BaseException:  # OSError:
                self.logger.debug("Mouse listener caught error pushing outlet, mouse move")

        def on_click(x, y, button, pressed):
            state = 1 if pressed else -1
            mysample = [x, y, state]
            try:
                self.outlet.push_sample(mysample)  # , timestamp=time.time())
            except BaseException:  # OSError:
                self.logger.debug("Mouse listener caught error pushing outlet, click")

        self.listener = mouse.Listener(on_move=on_move, on_click=on_click)

    def stop(self):
        if self.streaming:
            self.streaming = False
            self.listener.stop()
            self.logger.debug('Mouse: Stopped Listener')
