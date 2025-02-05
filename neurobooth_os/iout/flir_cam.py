# -*- coding: utf-8 -*-
import os.path as op
import numpy as np
import queue
import os
import threading
import uuid
import neurobooth_os.iout.metadator as meta
from typing import Callable, Any, Dict
import yaml

import cv2
import PySpin
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.iout.stim_param_reader import FlirDeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import make_db_logger
from neurobooth_os.msg.messages import DeviceInitialization, Request, NewVideoFile

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class FlirException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class VidRec_Flir:
    # def __init__(self,
    #              sizex=round(1936 / 2), sizey=round(1216 / 2), fps=196,
    #              camSN="20522874", exposure=4500, gain=20, gamma=.6,
    #              device_id="FLIR_blackfly_1", sensor_ids=['FLIR_rgb_1'], fd= .5):
    # Staging FLIR SN is 22348141
    def __init__(
            self,
            device_args: FlirDeviceArgs,
            exposure=4500,
            gain=20,
            gamma=0.6,
            fd=1,
    ):
        self.device_args: FlirDeviceArgs = device_args
        # not currently using sizex, sizey --> need to update to use these parameters
        # need to read these parameters from database
        # need new column in database that allows parameters in json file
        self.open = False
        self.serial_num = device_args.device_sn
        if self.serial_num is None:
            raise FlirException('FLIR serial number must be provided!')

        self.logger = make_db_logger()

        self.exposure = exposure
        self.gain = gain
        self.gamma = gamma
        self.device_id = device_args.device_id
        self.sensor_ids = device_args.sensor_ids
        self.fd = fd
        self.recording = False
        self.manifest_dict = {}

        self.get_cam()
        self.setup_cam()

        self.image_queue = queue.Queue(0)
        self.outlet = self.createOutlet()

        self.logger.debug(f'FLIR: fps={str(self.device_args.sample_rate())}; '
                          f'frame_size={str((self.device_args.width_px(), self.device_args.height_px()))}')

    def get_cam(self):
        self.system = PySpin.System.GetInstance()
        cam_list = self.system.GetCameras()
        self.cam = cam_list.GetBySerial(self.serial_num)

    def reset_cam(self) -> None:
        """
        During setup_cam, sometimes we get "GenICam::AccessException= Node is not writable." errors.
        This sequence of calls seems to get the camera into a clean state to resolve such issues.
        """
        self.cam.Init()
        self.cam.BeginAcquisition()
        self.cam.EndAcquisition()
        self.cam.DeInit()

    def try_setval(self, func: Callable, val: Any) -> None:
        try:
            func(val)
        except Exception as e:
            self.logger.error(f'FLIR: Error Setting Value [{func.__name__}({val})]: {e}')

    def setup_cam(self):
        self.cam.Init()
        self.open = True

        self.try_setval(self.cam.AcquisitionMode.SetValue, PySpin.AcquisitionMode_Continuous)
        self.try_setval(self.cam.ExposureAuto.SetValue, PySpin.ExposureAuto_Off)
        self.try_setval(self.cam.AcquisitionFrameRate.SetValue, self.device_args.sample_rate())
        self.try_setval(self.cam.Height.SetValue, self.device_args.height_px())
        self.try_setval(self.cam.Width.SetValue, self.device_args.width_px())
        self.try_setval(self.cam.OffsetX.SetValue, self.device_args.offset_x())
        self.try_setval(self.cam.OffsetY.SetValue, self.device_args.offset_y())
        self.try_setval(self.cam.ExposureTime.SetValue, self.exposure)
        self.try_setval(self.cam.Gamma.SetValue, self.gamma)
        self.try_setval(self.cam.Gain.SetValue, self.gain)
        self.try_setval(self.cam.BalanceWhiteAuto.SetValue, PySpin.BalanceWhiteAuto_Once)

        s_node_map = self.cam.GetTLStreamNodeMap()
        handling_mode = PySpin.CEnumerationPtr(
            s_node_map.GetNode("StreamBufferHandlingMode")
        )
        handling_mode_entry = handling_mode.GetEntryByName("NewestOnly")
        handling_mode.SetIntValue(handling_mode_entry.GetValue())
        # cam.BalanceWhiteAuto.SetValue(0)

    def createOutlet(self):
        self.streamName = "FlirFrameIndex"
        self.oulet_id = str(uuid.uuid4())
        info = set_stream_description(
            stream_info=StreamInfo(
                name=self.streamName,
                type="videostream",
                channel_format="double64",
                channel_count=2,
                source_id=self.oulet_id,
            ),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['FrameNum', 'Time_FLIR'],
            column_desc={
                'FrameNum': 'Frame number',
                'Time_FLIR': 'Camera timestamp (ns)',
            },
            serial_number=self.serial_num,
            fps_rgb=str(self.device_args.sample_rate()),
            exposure=str(self.exposure),
            gain=str(self.gain),
            gamma=str(self.gamma),
            # device_model_id=self.cam.get_device_name().decode(),
        )
        msg_body = DeviceInitialization(stream_name=self.streamName, outlet_id=self.oulet_id)
        with meta.get_database_connection() as db_conn:
            meta.post_message(Request(source='Flir', destination='CTR', body=msg_body), conn=db_conn)
        return StreamOutlet(info)

    # function to capture images, convert to numpy, send to queue, and release
    # from buffer in separate process
    def camCaptureVid(self):
        self.logger.debug('FLIR: Save Thread Started')
        while self.recording or self.image_queue.qsize():
            try:
                dequeuedImage = self.image_queue.get(block=True, timeout=1)
                self.video_out.write(dequeuedImage)
            except queue.Empty:
                continue
        self.logger.debug('FLIR: Exiting Save Thread')

    def start(self, name="temp_video"):
        self.prepare(name)
        self.video_thread = threading.Thread(target=self.record)
        self.logger.debug('FLIR: Beginning Recording')
        self.video_thread.start()

    def imgage_proc(self):
        im = self.cam.GetNextImage(2000)
        tsmp = im.GetTimeStamp()
        imgarr = im.GetNDArray()
        im_conv = cv2.demosaicing(imgarr, cv2.COLOR_BayerBG2BGR)
        im.Release()
        return cv2.resize(im_conv, None, fx=self.fd, fy=self.fd), tsmp

    def prepare(self, name="temp_video"):
        self.cam.BeginAcquisition()
        im, _ = self.imgage_proc()
        self.frameSize = (im.shape[1], im.shape[0])
        self.video_filename = "{}_flir.images".format(name)

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.FRAME_RATE_OUT = self.cam.AcquisitionResultingFrameRate()
        self.video_out = cv2.VideoWriter(
            self.video_filename, fourcc, self.FRAME_RATE_OUT, self.frameSize
        )
        msg_body = NewVideoFile(stream_name=self.streamName,
                                filename=op.split(self.video_filename)[-1])
        with meta.get_database_connection() as db_conn:
            meta.post_message(Request(source='Flir', destination='CTR', body=msg_body), conn=db_conn)
        self.streaming = True
        self.manifest_dict["frame_rate"] = self.FRAME_RATE_OUT
        self.manifest_dict['frame_height'] = im.shape[0]
        self.manifest_dict['frame_width'] = im.shape[1]
        self.manifest_dict['frame_depth'] = im.shape[2]

    def record(self):
        self.logger.debug('FLIR: LSL Thread Started')
        self.recording = True
        self.stamp = []
        self.frame_counter = 0

        # write flir manifest
        manifest_file_name = self.video_filename.replace(".images", "_manifest.yaml")
        self.manifest_dict["image_file"] = self.video_filename
        with open(manifest_file_name, "w") as file:
            yaml.dump(self.manifest_dict, file)

        with open(self.video_filename, 'wb', buffering=4096) as file:
            while self.recording:
                # Exception for failed waiting self.cam.GetNextImage(1000)
                try:
                    im, tsmp = self.imgage_proc()  # im is an nd_array that represents the image
                    arr_bytes = im.tobytes()
                    file.write(arr_bytes)
                except:
                    continue

                self.stamp.append(tsmp)

                try:
                    self.outlet.push_sample([self.frame_counter, tsmp])
                except BaseException:
                    self.logger.debug(f"Reopening FLIR {self.device_index} stream already closed")
                    self.outlet = self.createOutlet(self.video_filename)
                    self.outlet.push_sample([self.frame_counter, tsmp])
                self.frame_counter += 1

        self.cam.EndAcquisition()
        self.recording = False
        self.logger.debug('FLIR: Video File Released; Exiting LSL Thread')

    def stop(self):
        if self.open and self.recording:
            self.logger.debug('FLIR: Setting Record Stop Flag')
            self.recording = False
        self.streaming = False

    def close(self):
        self.stop()
        self.cam.DeInit()
        self.open = False

    def ensure_stopped(self, timeout_seconds: float) -> None:
        """Check to make sure the recording is actually stopped."""
        self.video_thread.join()
        if self.video_thread.is_alive():
            self.logger.error('FLIR: Potential Zombie Thread Detected!')
            raise FlirException('Potential Zombie Thread Detected!')


def read_bytes_to_avi(images_filename: str, video_out: cv2.VideoWriter, height, width, depth) -> None:
    """
    Reads the file containing the raw images and produces an AVI file encoded as MJPEG
    Parameters
    ----------
    images_filename  Name of file used to store the row frame data
    video_out        CV2 video writer
    height           frame height in pixels
    width            frame depth in pixels
    depth            frame depth

    Returns
    -------
    None
    """
    with open(images_filename, "rb") as f:
        byte_size = height * width * depth
        while True:
            chunk = f.read(byte_size)
            if chunk:
                bytes_1d = np.frombuffer(chunk, dtype=np.uint8)
                frame = np.reshape(bytes_1d, newshape=(height, width, depth))
                video_out.write(frame)
            else:
                return


def run_conversion(folder="E:/neurobooth/neurobooth_data/100001_2025-02-05") -> None:
    """
    Runs raw image file to AVI conversion for all image files in folder

    Returns
    -------
    None
    """

    logger = make_db_logger()
    logger.info(f'FLIR: Starting conversion in {folder}')

    manifests = []

    for file in os.listdir(folder):
        if file.endswith("flir_manifest.yaml"):
            manifests.append(os.path.join(folder, file))

        for manifest_filename in manifests:
            with open(manifest_filename, 'r') as file:
                manifest: Dict = yaml.safe_load(file)
                image_filename = manifest["image_file"]
                if os.path.exists(image_filename):

                    vid_width = manifest['frame_width']
                    vid_height = manifest['frame_height']
                    vid_depth = manifest['frame_depth']
                    frame_rate_out = manifest['frame_rate']

                    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                    frame_size = (vid_width, vid_height)  # images size in pixels

                    video_filename = image_filename.replace(".images", ".avi")
                    video_out = cv2.VideoWriter(
                        video_filename, fourcc, frame_rate_out, frame_size
                    )
                    read_bytes_to_avi(image_filename, video_out, vid_height, vid_width, vid_depth)
                    video_out.release()
                    if os.path.exists(video_filename):
                        os.remove(image_filename)
                        if os.path.exists(manifest_filename):
                            os.remove(manifest_filename)
                    logger.info(f'FLIR: Finished conversion in {folder}')
                else:
                    logger.error(f"Flir images file not found {image_filename}")



if __name__ == "__main__":
    run_conversion()
    # flir = VidRec_Flir()
    # print('Recording...')
    # flir.start()
    # time.sleep(10)
    # flir.stop()
    # print('Stopping...')
    # flir.ensure_stopped(timeout_seconds=5)
    # flir.close()
    # tdiff = np.diff(flir.stamp) / 1e6
    # print(f"diff range {np.ptp(tdiff):.2e}")
