import os.path as op
import threading
import uuid
import queue
import logging
from typing import Optional, ByteString
from timeit import default_timer as timer

import cv2
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.device import CameraPreviewer
from neurobooth_os.iout.stim_param_reader import WebcamDeviceArgs

from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os.msg.messages import DeviceInitialization, Request, NewVideoFile


class WebcamException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class VidRec_Webcam(CameraPreviewer):
    def __init__(
        self,
        device_args: WebcamDeviceArgs,
    ):
        self.device_args: WebcamDeviceArgs = device_args
        self.open: bool = False
        self.streaming: bool = False
        self.recording: bool = False

        self.camera: Optional[cv2.VideoCapture] = None
        self.video_filename: str = ''
        self.video_thread: Optional[threading.Thread] = None
        self.save_thread: Optional[threading.Thread] = None
        self.video_out: Optional[cv2.VideoWriter] = None

        self.frame_counter: int = 0
        self.image_queue = queue.Queue(0)
        self.timestamps: list[float] = []

        self.logger = logging.getLogger(APP_LOG_NAME)
        self.outlet = self.createOutlet()

        self.logger.debug(f'Webcam: fps={str(self.device_args.sample_rate())}; '
                          f'frame_size={str((self.device_args.width_px(), self.device_args.height_px()))}')

    def createOutlet(self) -> StreamOutlet:
        self.stream_name = "WebcamFrameIndex"
        self.outlet_id = str(uuid.uuid4())
        info = set_stream_description(
            stream_info=StreamInfo(
                name=self.stream_name,
                type="videostream",
                channel_format="double64",
                channel_count=2,
                source_id=self.outlet_id,
            ),
            device_id=self.device_args.device_id,
            sensor_ids=self.device_args.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['FrameNum', 'Time_ACQ'],
            column_desc={
                'FrameNum': 'Frame number',
                'Time_ACQ': 'System timestamp (s)',
            },
            camera_idx=str(self.device_args.camera_idx),
            fps_rgb=str(self.device_args.sample_rate()),
            size_rgb=str((self.device_args.width_px(), self.device_args.height_px())),
        )
        msg_body = DeviceInitialization(
            stream_name=self.stream_name,
            outlet_id=self.outlet_id,
            device_id=self.device_args.device_id,
            camera_preview=True,
        )
        with meta.get_database_connection() as db_conn:
            meta.post_message(Request(source='Webcam', destination='CTR', body=msg_body), conn=db_conn)
        return StreamOutlet(info)

    def open_stream(self) -> None:
        self.camera = cv2.VideoCapture(self.device_args.camera_idx, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            self.logger.error('Webcam: Could not open stream')
            raise WebcamException('Webcam: Could not open stream')
        self.open = True

    def close_stream(self) -> None:
        self.camera.release()
        self.open = False

    def save_to_disk(self) -> None:
        self.logger.debug('Webcam: Save Thread Started')
        while self.recording or self.image_queue.qsize():
            try:
                dequeuedImage = self.image_queue.get(block=True, timeout=1)
                self.video_out.write(dequeuedImage)
            except queue.Empty:
                continue
        self.logger.debug('Webcam: Exiting Save Thread')

    def start(self, name="temp_video") -> None:
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.logger.debug('Webcam: Beginning Recording')
        self.video_thread.start()

    def prepare(self, name="temp_video") -> None:
        self.open_stream()
        self.video_filename = f"{name}_webcam.avi"
        fourcc = cv2.VideoWriter_fourcc(*self.device_args.fourcc)
        fps = float(self.device_args.sample_rate())
        frame_size = (
            int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH)),
            int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        )
        self.video_out = cv2.VideoWriter(self.video_filename, fourcc, fps, frame_size)

        msg_body = NewVideoFile(stream_name=self.stream_name, filename=op.split(self.video_filename)[-1])
        with meta.get_database_connection() as db_conn:
            meta.post_message(Request(source='Webcam', destination='CTR', body=msg_body), conn=db_conn)
        self.streaming = True

    def record(self) -> None:
        self.logger.debug('Webcam: LSL Thread Started')
        self.recording = True
        self.frame_counter = 0
        self.save_thread = threading.Thread(target=self.save_to_disk)
        self.save_thread.start()

        self.timestamps = []
        while self.recording:
            rc, img = self.camera.read()
            tsmp = timer()
            if not rc:
                continue

            self.image_queue.put(img)
            self.timestamps.append(tsmp)

            try:
                self.outlet.push_sample([self.frame_counter, tsmp])
            except BaseException:
                self.logger.debug(f"Reopening Webcam {self.device_args.device_index} stream already closed")
                self.outlet = self.createOutlet()
                self.outlet.push_sample([self.frame_counter, tsmp])

            self.frame_counter += 1
            if not self.frame_counter % 1000 and self.image_queue.qsize() > 2:
                self.logger.debug(
                    f"Webcam queue length is {self.image_queue.qsize()} frame count: {self.frame_counter}"
                )

        self.close_stream()
        self.recording = False
        self.save_thread.join()
        self.video_out.release()
        self.logger.debug('Webcam: Video File Released; Exiting LSL Thread')

    def stop(self) -> None:
        if self.open and self.recording:
            self.logger.debug('Webcam: Setting Record Stop Flag')
            self.recording = False
        self.streaming = False

    def close(self) -> None:
        self.stop()

    def ensure_stopped(self, timeout_seconds: float) -> None:
        """Check to make sure the recording is actually stopped."""
        self.video_thread.join()
        if self.video_thread.is_alive():
            self.logger.error('Webcam: Potential Zombie Thread Detected!')
            raise WebcamException('Potential Zombie Thread Detected!')

    def frame_preview(self) -> ByteString:
        """
        Retrieve a frame preview from the webcam.

        :returns: The raw data of the image/frame, or an empty byte string if an error occurs.
        """
        self.open_stream()
        rc1, img = self.camera.read()
        self.close_stream()
        rc2, img = cv2.imencode('.png', img)
        return img.tobytes() if (rc1 and rc2) else b""


def test_script() -> None:
    import neurobooth_os.config as cfg
    from neurobooth_os.iout.stim_param_reader import StandardSensorArgs
    from time import sleep
    import numpy as np

    cfg.load_config()
    args = WebcamDeviceArgs(
        device_name='webcam',
        device_id='WebcamDev',
        sensor_array=[StandardSensorArgs(
            sensor_id='Webcam1',
            file_type='.avi',
            arg_parser='',
            sample_rate=60,
            width_px=1920,
            height_px=1080,
            ENV_devices={}
        )],
        sensor_ids=['Webcam1'],
        fourcc='MJPG',
        ENV_devices={'WebcamDev': {'camera_idx': 0}},
        wearable_bool=False,
        arg_parser='',
    )

    print('Beginning Capture')
    webcam = VidRec_Webcam(device_args=args)
    webcam.start('test_video')
    sleep(5)
    print('Ending Capture')
    webcam.stop()
    sleep(0.5)
    webcam.ensure_stopped(0.5)

    timestamps = np.array(webcam.timestamps) * 1000  # s to ms
    delta = np.diff(timestamps)
    print(f'Timestamp delta mean={delta.mean():.2f}, std={delta.std():.2f}')

if __name__ == "__main__":
    test_script()