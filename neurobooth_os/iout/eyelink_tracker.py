import os.path as op
import time
import uuid
import threading
import subprocess
import logging
import numpy as np

import pylink
from psychopy import visual, monitors
from pylsl import StreamInfo, StreamOutlet, local_clock
from psychopy import core

from neurobooth_os.tasks.smooth_pursuit.EyeLinkCoreGraphicsPsychoPy import (
    EyeLinkCoreGraphicsPsychoPy,
)
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME

class EyeTracker:
    def __init__(
        self,
        sample_rate=1000,
        calibration_type="HV5",
        win=None,
        with_lsl=True,
        ip="192.168.100.15",
        device_id="Eyelink_1",
        sensor_ids=["Eyelink_sens_1"],
    ):

        self.IP = ip
        self.sample_rate = sample_rate
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self.streamName = "EyeLink"
        self.with_lsl = with_lsl
        mon = monitors.getAllMonitors()[0]
        self.mon_size = monitors.Monitor(mon).getSizePix()
        self.calibration_type = calibration_type

        if win is None:
            customMon = monitors.Monitor(
                "demoMon", width=55, distance=60
            )  # distance subject to screen specified in task/utils:make_win() here just for testing
            self.win = visual.Window(
                self.mon_size, fullscr=False, monitor=customMon, units="pix"
            )
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False

        # Setup outlet stream info
        self.oulet_id = str(uuid.uuid4())
        self.stream_info = set_stream_description(
            stream_info=StreamInfo("EyeLink", "Gaze", 13, self.sample_rate, "double64", self.oulet_id),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 1),
            columns=[
                'R_GazeX', 'R_GazeY', 'R_PupilSize',
                'L_GazeX', 'L_GazeY', 'L_PupilSize',
                'Target_PositionX', 'Target_PositionY', 'Target_Distance',
                'ResolutionX', 'ResolutionY',
                'Time_EDF', 'Time_NUC'
            ],
            column_desc={
                'R_GazeX': 'Right eye: Horizontal gaze location on screen (pixels)',
                'R_GazeY': 'Right eye: Vertical gaze location on screen (pixels)',
                'R_PupilSize': 'Right eye: Pupil size (arbitrary units; see EyeLink documentation)',
                'L_GazeX': 'Left eye: Horizontal gaze location on screen (pixels)',
                'L_GazeY': 'Left eye: Vertical gaze location on screen (pixels)',
                'L_PupilSize': 'Left eye: Pupil size (arbitrary units; see EyeLink documentation)',
                'Target_PositionX': 'Horizontal location of the bullseye target (camera pixels)',
                'Target_PositionY': 'Vertical location of the bullseye target (camera pixels)',
                'Target_Distance': 'Distance to the bullseye target',
                'ResolutionX': 'Horizontal angular resolution at current gaze position (pixels per visual degree)',
                'ResolutionY': 'Vertical angular resolution at current gaze position (pixels per visual degree)',
                'Time_EDF': 'Timestamp within the EDF file (ms)',
                'Time_NUC': 'Local timestamp of sample receipt by the NUC machine (s)',
            },
            fps=str(self.sample_rate),
        )
        self.outlet = StreamOutlet(self.stream_info)

        self.logger = logging.getLogger(APP_LOG_NAME)
        self.logger.debug(f'EyeLink: sample_rate={str(self.sample_rate)}')

        print(f"-OUTLETID-:{self.streamName}:{self.oulet_id}")
        self.streaming = False
        self.calibrated = True
        self.recording = False
        self.paused = True
        self.connect_tracker()

    def connect_tracker(self):
        try:
            self.tk = pylink.EyeLink(self.IP)
        except RuntimeError:
            msg_text = f"RuntimeError: Could not connect to tracker at %s. " \
                       "Please be sure to start Eyetracker before starting Neurobooth." % self.IP
            print(msg_text)
            self.logger.error(msg_text)

        if self.IP is not None:
            self.tk.setAddress(self.IP)
        # # Open an EDF data file on the Host PC
        # self.tk.openDataFile('ev_test.edf')

        self.tk.setOfflineMode()
        pylink.msecDelay(50)
        self.tk.sendCommand(f"sample_rate {self.sample_rate}")

        # File and Link data control
        # what eye events to save in the EDF file, include everything by default
        file_event_flags = "LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT"
        # what eye events to make available over the link, include everything by default
        link_event_flags = "LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON,FIXUPDATE,INPUT"
        # what sample data to save in the EDF data file and to make available
        # over the link, include the 'HTARGET' flag to save head target sticker
        # data for supported eye trackers

        file_sample_flags = (
            "LEFT,RIGHT,GAZE,HREF,RAW,AREA,HTARGET,GAZERES,BUTTON,STATUS,INPUT"
        )
        link_sample_flags = (
            "LEFT,RIGHT,GAZE,GAZERES,PUPIL,HREF,AREA,HTARGET,STATUS,INPUT"
        )

        self.tk.sendCommand("file_event_filter = %s" % file_event_flags)
        self.tk.sendCommand("file_sample_data = %s" % file_sample_flags)
        self.tk.sendCommand("link_event_filter = %s" % link_event_flags)
        self.tk.sendCommand("link_sample_data = %s" % link_sample_flags)

        # Pass screen resolution  to the tracker
        self.tk.sendCommand(
            f"screen_pixel_coords = 0 0 {self.mon_size[0]-1} {self.mon_size[1]-1}"
        )

        # Send a DISPLAY_COORDS message so Data Viewer knows the correct screen size
        self.tk.sendMessage(
            f"DISPLAY_COORDS = 0 0 {self.mon_size[0]-1} {self.mon_size[1]-1}"
        )

        # Choose a calibration type, H3, HV3, HV5, HV13 (HV = horizontal/vertical)
        self.tk.sendCommand(f"calibration_type = {self.calibration_type }")

        self.tk.sendCommand("calibration_area_proportion = 0.80 0.78")
        self.tk.sendCommand("validation_area_proportion = 0.80 0.78")

    def calibrate(self):
        self.logger.debug('EyeLink: Performing Calibration')
        calib_prompt = "You will see dots on the screen, please gaze at them"
        calib_msg = visual.TextStim(
            self.win, text=calib_prompt, color="white", units="pix"
        )
        calib_msg.draw()
        self.win.flip()

        pylink.closeGraphics()
        graphics = EyeLinkCoreGraphicsPsychoPy(self.tk, self.win)
        pylink.openGraphicsEx(graphics)

        # Calibrate the tracker
        self.tk.doTrackerSetup()
        self.calibrated = True
        prompt = "Calibration finished"
        prompt_msg = visual.TextStim(self.win, text=prompt, color="Black", units="pix")
        prompt_msg.draw()
        self.win.flip()

    def edf_to_ascii(self):
        fname_asc = self.filename.replace(".edf", ".asc")
        if not op.exists(fname_asc):
            pout = subprocess.run(["edf2asc.exe", self.filename], shell=True)
            if not pout.stderr:
                print(f"-new_filename-:{self.streamName}:{op.split(fname_asc)[-1]}")
        else:
            print(f"FILE {fname_asc} already exists")
        return

    def start(self, filename="TEST.edf"):
        self.filename = filename
        print(f"-new_filename-:{self.streamName}:{op.split(filename)[-1]}")
        self.fname_temp = "name8chr.edf"
        self.tk.openDataFile(self.fname_temp)
        self.streaming = True

        pylink.beginRealTimeMode(100)
        self.tk.startRecording(1, 1, 1, 1)
        # print("Eyetracker recording")
        self.recording = True
        self.stream_thread = threading.Thread(target=self.record)
        self.logger.debug('EyeLink: Starting Record Thread')
        self.stream_thread.start()

    def record(self):
        # print("Eyetracker LSL recording")
        self.paused = False
        old_sample = None
        values = []
        self.timestamps_et = []
        self.timestamps_local = []

        self.logger.debug('EyeLink: Entering LSL Loop')
        while self.recording:
            if self.paused:
                t1 = local_clock()
                t2 = t1
                while t2 - t1 < 1 / (self.sample_rate * 4):
                    t2 = local_clock()
                continue

            t1 = local_clock()
            t2 = t1

            smp = self.tk.getNewestSample()  # check smp object, see et.tk.getNextData()
            if smp is not None:
                if old_sample is None or old_sample.getTime() != smp.getTime():
                    ppd = smp.getPPD()
                    timestamp = smp.getTime()
                    timestamp_local = local_clock()
                    self.timestamps_et.append(timestamp)
                    self.timestamps_local.append(timestamp_local)

                    values = [
                        0, 0, 0,  # Right eye position and pupil size
                        0, 0, 0,  # Left eye position and pupil size
                        smp.getTargetX(), smp.getTargetY(), smp.getTargetDistance(),  # Forehead target location
                        ppd[0], ppd[1],  # Resolution
                        timestamp, timestamp_local,  # Timing
                    ]

                    # Grab gaze & pupil size data
                    if smp.isRightSample():
                        gaze = smp.getRightEye().getGaze()
                        pupil = smp.getRightEye().getPupilSize()  # pupil size
                        values[:3] = [gaze[0], gaze[1], pupil]
                    if smp.isLeftSample():
                        gaze = smp.getLeftEye().getGaze()
                        pupil = smp.getLeftEye().getPupilSize()
                        values[3:6] = [gaze[0], gaze[1], pupil]

                    self.outlet.push_sample(values)
                    old_sample = smp

            while t2 - t1 < 1 / (self.sample_rate * 4):
                t2 = local_clock()

        fps_et = np.mean(1 / np.diff(self.timestamps_et))
        fps_lcl = np.mean(1 / np.diff(self.timestamps_local))
        print(
            f"ET number of samples {len(self.timestamps_et)}, fps et: {fps_et}, fps local: {fps_lcl}"
        )
        self.tk.stopRecording()
        self.tk.closeDataFile()
        self.logger.debug('EyeLink: Exiting Record Thread')

    def stop(self):
        self.logger.debug('EyeLink: Setting Stop Signal')
        self.recording = False
        if self.streaming:
            self.stream_thread.join()
            # print("Eyelink stoped recording, downaloading edf")
            self.tk.receiveDataFile(self.fname_temp, self.filename)
            self.edf_to_ascii()
            self.streaming = False

    def close(self):
        if self.recording:
            self.stop()
        self.tk.close()


if __name__ == "__main__":
    from neurobooth_os.tasks.utils import countdown

    et = EyeTracker()
    et.start()
    countdown(10)
    # pylink.msecDelay(10000)
    et.stop()
    et.win.close()

    import matplotlib.pyplot as plt
    import numpy as np

    timestamps_et = [e / 1000 for e in et.timestamps_et]
    plt.figure()
    plt.plot(np.diff(timestamps_et))
    plt.plot(np.diff(et.timestamps_local), alpha=0.5)

    print(
        f"ET fps {1/np.mean(np.diff(timestamps_et))}, lsl fps {1/np.mean(np.diff(et.timestamps_local))}"
    )
    print(f"ET samples {len(timestamps_et)}, lsl samples {len(et.timestamps_local)}")
