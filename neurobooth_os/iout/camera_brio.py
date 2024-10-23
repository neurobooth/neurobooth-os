import os
import sys
import threading
import uuid
import time
import functools

import cv2
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout import dshowcapture
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
import neurobooth_os.iout.metadator as meta

import warnings

from neurobooth_os.msg.messages import Request, DeviceInitialization

warnings.filterwarnings("ignore")


def catch_exception(f):
    @functools.wraps(f)
    def func(*args, **kwargs):
        # try:
        return f(*args, **kwargs)
        # except Exception as e:
        #     print('Caught an exception in function "{}" of type {}'.format(f.__name__, e))

    return func


class VidRec_Brio:
    def __init__(
        self,
        fourcc=cv2.VideoWriter_fourcc(*"MJPG"),
        sizex=1280,
        sizey=720,
        fps=90,
        camindex=0,
        mode=33,
        doPreview=False,
    ):
        # sizex=640, sizey=480, fps=120, camindex=0, mode=19, doPreview=False):

        self.open = True
        self.doPreview = doPreview
        self.previewing = False
        self.recording = False
        self.streaming = False
        self.device_index = camindex
        self.fps = (
            fps  # fps should be the minimum constant rate at which the camera can
        )
        # capture images (with no decrease in speed over time; testing is required)
        self.fourcc = fourcc
        # scale_percent = 50
        # self.frameSize = (int(sizex * scale_percent / 100), int(sizey *
        # scale_percent / 100)) # video formats and sizes also depend and vary
        # according to the camera used
        self.frameSize = (sizex, sizey)
        print(f"Frame size : {self.frameSize}")
        self.video_cap = dshowcapture.DShowCapture()
        self.mode = mode
        self.device_name = self.video_cap.get_info()[self.device_index]["name"]
        self.capture_cap()

        if doPreview:
            self.preview_fps = 10
            self.preview_outlet_id = str(uuid.uuid4())
            self.info_stream = StreamInfo(
                "Webcam",
                "Experiment",
                320 * 240,
                self.preview_fps,
                "int32",
                self.preview_outlet_id,
            )
            self.outlet_preview = StreamOutlet(self.info_stream)
            msg_body = DeviceInitialization(stream_name=self.streamName, outlet_id=self.outlet_id)
            with meta.get_database_connection() as conn:
                meta.post_message(Request(source='VidRec_Brio', destination='CTR', body=msg_body), conn=conn)

            self.preview_start()
            self.preview_relFps = round(fps / self.preview_fps)

    def capture_cap(self):
        self.video_cap.capture_device_by_dcap(
            self.device_index, self.mode, self.frameSize[0], self.frameSize[1], self.fps
        )
        print(f"Brio {self.device_index} capture started")

    @catch_exception
    def createOutlet(self, filename):
        streamName = f"BrioFrameIndex_{self.device_index}"
        self.oulet_id = str(uuid.uuid4())
        info = set_stream_description(
            stream_info=StreamInfo(
                name=streamName,
                type="videostream",
                channel_format="int32",
                channel_count=1,
                source_id=self.oulet_id,
            ),
            device_id='camera_brio',
            sensor_ids=[f'camera_brio_{self.device_index}'],
            data_version=DataVersion(1, 0),
            columns=['FrameNum'],
            column_desc={'FrameNum': 'Locally-tracked frame number'},
            video_file=filename,
            size_rgb=str(self.frameSize),
            fps_rgb=str(self.fps),
            device_name=self.device_name,
        )
        msg_body = DeviceInitialization(stream_name=streamName, outlet_id=self.oulet_id)
        with meta.get_database_connection() as conn:
            meta.post_message(Request(source='VidRec_Brio', destination='CTR', body=msg_body), conn=conn)

        return StreamOutlet(info)

    @catch_exception
    def preview(self):
        # Streams camera content while not recording to file
        print(f"Brio {self.device_index} preview stream started")
        while self.previewing:
            frame = self.video_cap.get_frame(1000)
            if frame is not None:
                frame = self.frame_preview(frame)
                try:
                    self.outlet_preview.push_sample(frame.flatten())
                except BaseException:  # "OSError" from C++
                    print(
                        "Reopening Brio {self.device_index} preview stream already closed"
                    )
                    self.outlet_preview = StreamOutlet(self.info_stream)
                    self.outlet_preview.push_sample(frame.flatten())

            key = cv2.waitKey(20)
            if key == 27:  # exit on ESC
                break

            time.sleep(1 / self.preview_fps)

    #        self.outlet.__del__()

    @catch_exception
    def frame_preview(self, frame):
        frame = cv2.resize(frame, (320, 240))
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return frame

    @catch_exception
    def preview_start(self):
        if self.doPreview:
            if self.video_cap.capturing() is False:
                self.capture_cap()
            self.previewing = True
            self.preview_thread = threading.Thread(target=self.preview)
            self.preview_thread.start()

    @catch_exception
    def start(self, name="temp_video"):
        if self.video_cap.capturing() is False:
            self.capture_cap()
        self.previewing = False
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.video_thread.start()

    @catch_exception
    def prepare(self, name="temp_video"):
        self.video_filename = "{}_brio{}.avi".format(name, self.device_index)
        self.video_out = cv2.VideoWriter(
            self.video_filename, self.fourcc, self.fps, self.frameSize
        )
        self.outlet = self.createOutlet(self.video_filename)
        self.streaming = True

    @catch_exception
    def record(self):
        self.recording = True
        self.frame_counter = 0
        print(f"Brio {self.device_index} recording {self.video_filename}")
        while self.recording:
            if self.video_cap.capturing():
                self.frame_counter += 1
                frame = self.video_cap.get_frame(1000)
                try:
                    self.outlet.push_sample([self.frame_counter])
                except BaseException:  # "OSError" from C++
                    print(f"Reopening brio {self.device_index} stream already closed")
                    self.outlet = self.createOutlet(self.video_filename)
                    self.outlet.push_sample([self.frame_counter])
                # frame = cv2.resize(frame, self.frameSize)
                self.video_out.write(frame)

                if self.doPreview:
                    # Push frame every relative Fps
                    if (self.frame_counter % self.preview_relFps) == 0:
                        frame = self.frame_preview(frame)
                        try:
                            self.outlet_preview.push_sample(frame.flatten())
                        except BaseException:  # "OSError" from C++
                            print(
                                f"Reopening brio {self.device_index} preview stream already closed"
                            )
                            self.outlet_preview = StreamOutlet(self.info_stream)
                            self.outlet_preview.push_sample(frame.flatten())

        print(
            f"Brio {self.device_index} recording ended with {self.frame_counter} frames"
        )
        self.video_out.release()

    #        self.outlet.__del__()

    @catch_exception
    def stop(self):
        if self.open and self.recording:
            self.recording = False
            self.preview_start()
        #            self.outlet.__del__()
        self.streaming = False

    @catch_exception
    def close(self):
        if self.previewing:
            self.previewing = False
            time.sleep(1 / self.preview_fps)

        self.stop()
        time.sleep(0.5)
        if self.video_cap.cap:
            self.video_cap.stop_capture()
        self.video_cap.destroy_capture()
        self.open = False
        print(f"Brio cam {self.device_index} capture closed")


#        if self.doPreview:
#            self.outlet_preview.__del__()


# if __name__ == "__main__":
#     cam_dict = [{'name': 'cam_0', 'index': 0}]
#     record_dir = r'C:\git\neurobooth-eel'
#     participant='Montag'
#     videocapture = ViedoCapture(cam_dict)
#     videocapture.init(record_dir, participant)
#     ##self.videocapture.stopRecording()
#     cap = threading.Thread(target=videocapture.capture)
#     cap.start()
