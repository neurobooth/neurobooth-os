# -*- coding: utf-8 -*-
import os.path as op
import numpy as np
import queue
import time
import os
import threading
import uuid
import logging
import multiprocessing
from typing import Callable, Any

import cv2
import PySpin
from pylsl import StreamInfo, StreamOutlet

import neurobooth_os.iout.metadator as meta
from neurobooth_os.iout.stim_param_reader import FlirDeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os.msg.messages import DeviceInitialization, Request, NewVideoFile

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


def camCaptureVid(video_filename, frame_rate, frame_size, image_queue, recording):
    logger = logging.getLogger(APP_LOG_NAME)
    logger.debug('FLIR: Save Process Started')

    try:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        video_out = cv2.VideoWriter(video_filename, fourcc, frame_rate, frame_size)

        while recording or not image_queue.empty():
            try:
                dequeuedImage = image_queue.get(block=True, timeout=1)
                video_out.write(dequeuedImage)
            except queue.Empty:
                continue
    except Exception as e:
        logger.error(f'FLIR: Error in save process: {e}')
    finally:
        video_out.release()
        logger.debug('FLIR: Video File Released; Exiting Save Process')


class FlirException(Exception):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class VidRec_Flir:
    def __init__(
            self,
            device_args: FlirDeviceArgs,
            exposure=4500,
            gain=20,
            gamma=0.6,
            fd=1,
    ):
        self.frame_counter = None
        self.save_process = None
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
        self.image_queue = multiprocessing.Queue(0)
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
    # def camCaptureVid(self, video_filename, frame_rate, frame_size, image_queue, recording):
    #     logger = logging.getLogger(APP_LOG_NAME)
    #     logger.debug('FLIR: Save Process Started')
    #
    #     try:
    #         fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    #         video_out = cv2.VideoWriter(video_filename, fourcc, frame_rate, frame_size)
    #
    #         while recording or not image_queue.empty():
    #             try:
    #                 dequeuedImage = image_queue.get(block=True, timeout=1)
    #                 video_out.write(dequeuedImage)
    #             except queue.Empty:
    #                 continue
    #     except Exception as e:
    #         logger.error(f'FLIR: Error in save process: {e}')
    #     finally:
    #         video_out.release()
    #         logger.debug('FLIR: Video File Released; Exiting Save Process')

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

        self.FRAME_RATE_OUT = self.cam.AcquisitionResultingFrameRate()
        msg_body = NewVideoFile(stream_name=self.streamName,
                                filename=op.split(self.video_filename)[-1])
        with meta.get_database_connection() as db_conn:
            meta.post_message(Request(source='Flir', destination='CTR', body=msg_body), conn=db_conn)
        self.streaming = True

    def record(self):
        self.logger.debug('FLIR: LSL Thread Started')
        self.recording = True
        self.frame_counter = 0
        with multiprocessing.Manager() as manager:
            recording = manager.Value('b', True)
            try:
                self.save_process = multiprocessing.Process(target=camCaptureVid,
                                                            args=(self.video_filename,
                                                                  self.FRAME_RATE_OUT,
                                                                  self.frameSize,
                                                                  queue,
                                                                  recording))
                self.save_process.start()
            except BaseException as e:
                self.logger.error(f'Unable to start Flir save process; error={e}')

            self.stamp = []
            while self.recording:
                # Exception for failed waiting self.cam.GetNextImage(1000)
                try:
                    im, tsmp = self.imgage_proc()
                except:
                    continue

                try:
                    self.image_queue.put(im)
                except BaseException as e:
                    self.logger.critical(f'Unable to enqueue Flir frame; error={e}')
                    raise e

                self.stamp.append(tsmp)

                try:
                    self.outlet.push_sample([self.frame_counter, tsmp])
                except BaseException:
                    self.logger.debug(f"Reopening FLIR {self.device_index} stream already closed")
                    self.outlet = self.createOutlet(self.video_filename)
                    self.outlet.push_sample([self.frame_counter, tsmp])

                self.frame_counter += 1

                if not self.frame_counter % 1000 and self.image_queue.qsize() > 2:
                    self.logger.debug(
                        f"Queue length is {self.image_queue.qsize()} frame count: {self.frame_counter}"
                    )
        self.cam.EndAcquisition()
        self.recording = False
        recording.value = False
        self.save_process.join()
        self.logger.debug('FLIR: Exiting LSL Thread')

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
        self.video_thread.join(timeout_seconds)
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
