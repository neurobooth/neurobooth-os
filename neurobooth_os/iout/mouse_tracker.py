import uuid

from pynput import mouse
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


class MouseStream:
    def __init__(self, device_id="Mouse", sensor_ids=["Mouse"]):

        self.oulet_id = str(uuid.uuid4())
        self.info_stream = set_stream_description(
            stream_info=StreamInfo(
                name="Mouse",
                type="mouse",
                channel_count=3,
                channel_format="int32",
                source_id=self.oulet_id,
            ),
            device_id=device_id,
            sensor_ids=sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['PosX', 'PosY', 'MouseState'],
            column_desc={
                'PosX': 'X screen coordinate of the mouse (pixels)',
                'PosY': 'y screen coordinate of the mouse (pixels)',
                'MouseState': 'Flag for the state of the mouse (0=move, 1=click, -1=release)',
            }
        )
        self.outlet = StreamOutlet(self.info_stream)
        print(f"-OUTLETID-:Mouse:{self.oulet_id}")
        self.streaming = False

    def start(self):
        self.streaming = True
        self.stream()
        self.listener.start()

        try:
            self.outlet.push_sample([0, 0, 0])
        except BaseException:  # "OSError" from C++
            print("Mouse stream already closed, reopening")
            self.outlet = StreamOutlet(self.info_stream)

    def stream(self):
        def on_move(x, y):
            mysample = [x, y, 0]
            try:
                self.outlet.push_sample(mysample)  # , timestamp=time.time())
            except BaseException:  # OSError:
                print("Mouse listner caugh error pushing oulet, mouse move")

        def on_click(x, y, button, pressed):
            state = 1 if pressed else -1
            mysample = [x, y, state]
            try:
                self.outlet.push_sample(mysample)  # , timestamp=time.time())
            except BaseException:  # OSError:
                print("Mouse listner caugh error pushing oulet, click")

        self.listener = mouse.Listener(on_move=on_move, on_click=on_click)

    def stop(self):
        if self.streaming:
            self.streaming = False
            self.listener.stop()
            print("Mouse capture stopped")
