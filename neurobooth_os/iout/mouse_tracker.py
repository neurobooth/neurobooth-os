import uuid

from pynput import mouse
from pylsl import StreamInfo, StreamOutlet


class MouseStream():
    def __init__(self, device_id="Mouse", sensor_ids=["Mouse"]):

        self.oulet_id = str(uuid.uuid4())
        info_stream = StreamInfo(name='Mouse', type='mouse', channel_count=3,                                 
                                 channel_format='int32', source_id=self.oulet_id)

        self.info_stream = info_stream
        
        self.info_stream.desc().append_child_value("device_id", device_id)
        self.info_stream.desc().append_child_value("sensor_ids", str(sensor_ids))
        
        self.outlet = StreamOutlet(info_stream)
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

