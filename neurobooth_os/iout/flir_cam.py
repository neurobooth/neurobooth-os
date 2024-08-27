# -*- coding: utf-8 -*-
import os.path as op
import numpy as np
import queue
import time
import os
import threading
import uuid
import neurobooth_os.iout.metadator as meta
import logging
from typing import Callable, Any

import cv2
import PySpin
from pylsl import StreamInfo, StreamOutlet
import skvideo
import skvideo.io
import h5py

from neurobooth_os.iout.stim_param_reader import FlirDeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os.msg.messages import DeviceInitialization, Request

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

        self.logger = logging.getLogger(APP_LOG_NAME)

        self.exposure = exposure
        self.gain = gain
        self.gamma = gamma
        self.device_id = device_args.device_id
        self.sensor_ids = device_args.sensor_ids
        self.fd = fd
        self.recording = False

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
        db_conn = meta.get_database_connection()
        msg_body = DeviceInitialization(stream_name=self.streamName, outlet_id=self.oulet_id)
        meta.post_message(Request(source='', destination='CTR', body=msg_body), conn=db_conn)
        # print(f"-OUTLETID-:{self.streamName}:{self.oulet_id}")
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
        self.video_filename = "{}_flir.avi".format(name)

        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        self.FRAME_RATE_OUT = self.cam.AcquisitionResultingFrameRate()
        self.video_out = cv2.VideoWriter(
            self.video_filename, fourcc, self.FRAME_RATE_OUT, self.frameSize
        )
        print(f"-new_filename-:{self.streamName}:{op.split(self.video_filename)[-1]}")

        self.streaming = True

    def record(self):
        self.logger.debug('FLIR: LSL Thread Started')
        self.recording = True
        self.frame_counter = 0
        self.save_thread = threading.Thread(target=self.camCaptureVid)
        self.save_thread.start()

        self.stamp = []
        while self.recording:
            # Exception for failed waiting self.cam.GetNextImage(1000)
            try:
                im, tsmp = self.imgage_proc()
            except:
                continue

            self.image_queue.put(im)
            self.stamp.append(tsmp)

            try:
                self.outlet.push_sample([self.frame_counter, tsmp])
            except BaseException:
                print(f"Reopening FLIR {self.device_index} stream already closed")
                self.outlet = self.createOutlet(self.video_filename)
                self.outlet.push_sample([self.frame_counter, tsmp])

            # self.video_out.write(im_conv_d)
            self.frame_counter += 1

            if not self.frame_counter % 1000 and self.image_queue.qsize() > 2:
                print(
                    f"Queue length is {self.image_queue.qsize()} frame count: {self.frame_counter}"
                )

        # print(f"FLIR recording ended with {self.frame_counter} frames in {time.time()-t0}")
        self.cam.EndAcquisition()
        self.recording = False
        self.save_thread.join()
        self.video_out.release()
        self.logger.debug('FLIR: Video File Released; Exiting LSL Thread')
        # print(f"FLIR video saving ended in {time.time()-t0} sec")

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


if __name__ == "__main__":
    flir = VidRec_Flir()
    print('Recording...')
    flir.start()
    time.sleep(10)
    flir.stop()
    print('Stopping...')
    flir.ensure_stopped(timeout_seconds=5)
    flir.close()
    tdiff = np.diff(flir.stamp) / 1e6
    print(f"diff range {np.ptp(tdiff):.2e}")
