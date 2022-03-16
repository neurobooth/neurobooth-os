import os.path as op
import time
import uuid
import threading

import pylink
from psychopy import visual, monitors
from pylsl import StreamInfo, StreamOutlet

from neurobooth_os.tasks.smooth_pursuit.EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy


class EyeTracker():

    def __init__(
            self,
            sample_rate=1000,
            monitor_width=55,
            monitor_distance=65,
            calibration_type="HV5",
            win=None,
            with_lsl=True,
            ip='192.168.100.15',
            device_id="Eyelink_1",
            sensor_ids=['Eyelink_sens_1']):
        
        self.IP = ip
        self.sample_rate = sample_rate
        self.monitor_width = monitor_width
        self.monitor_distance = monitor_distance
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self.streamName = "EyeLink"
        self.with_lsl = with_lsl
        mon = monitors.getAllMonitors()[0]
        self.mon_size = monitors.Monitor(mon).getSizePix()
        self.calibration_type = calibration_type

        if win is None:
            customMon = monitors.Monitor('demoMon', width=monitor_width, distance=monitor_distance)
            self.win = visual.Window(self.mon_size, fullscr=False, monitor=customMon, units='pix')
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False

        # Setup outlet stream info
        self.oulet_id = str(uuid.uuid4())
        self.stream_info = StreamInfo('EyeLink','Gaze', 12, self.sample_rate, 'float32', self.oulet_id)
        self.stream_info.desc().append_child_value("fps", str(self.sample_rate))
        self.stream_info.desc().append_child_value("device_id", self.device_id)
        self.stream_info.desc().append_child_value("sensor_ids", str(self.sensor_ids))
        col_names = ['R_gazeX', 'R_gazeY', 'R_pupil','L_gazeX', 'L_gazeY', 'L_pupil', 'TargetDistance',
                     'TargetPosition', 'PPD', 'timestamp']
        self.stream_info.desc().append_child_value("column_names", str(col_names))
        self.stream_info.desc().append_child_value("gaze", "location gaze in the screen in pixels")
        self.stream_info.desc().append_child_value("pupil", "size pupil")
        self.stream_info.desc().append_child_value("TargetDistance", "distance subject target sticker to screen")
        self.stream_info.desc().append_child_value("TargetPosition", "location subject target sticker in eyetracker " + \
                                                    "camera space, quantifies movement")
        self.stream_info.desc().append_child_value("PPD", " Angular resolution at current gaze position in screen pixels per" + \
                                                   "visual degree (from gaze to deg visual angle)")
        self.stream_info.desc().append_child_value('timestamp', "eyetracker timestamp of the sample")
        self.outlet = StreamOutlet(self.stream_info)
        
        print(f"-OUTLETID-:{self.streamName}:{self.oulet_id}")
        self.streaming = False
        self.calibrated = True
        self.recording = False
        self.paused = True
        self.connect_tracker()

    def connect_tracker(self):
        self.tk = pylink.EyeLink(self.IP)
        if self.IP is not None:
            self.tk.setAddress(self.IP)
        # # Open an EDF data file on the Host PC
        # self.tk.openDataFile('ev_test.edf')

        self.tk.setOfflineMode()
        pylink.msecDelay(50)
        self.tk.sendCommand(f'sample_rate {self.sample_rate}')
        
        # File and Link data control
        # what eye events to save in the EDF file, include everything by default
        file_event_flags = 'LEFT,RIGHT,FIXATION,SACCADE,BLINK,MESSAGE,BUTTON,INPUT'
        # what eye events to make available over the link, include everything by default
        link_event_flags = 'LEFT,RIGHT,FIXATION,SACCADE,BLINK,BUTTON,FIXUPDATE,INPUT'
        # what sample data to save in the EDF data file and to make available
        # over the link, include the 'HTARGET' flag to save head target sticker
        # data for supported eye trackers
        
        file_sample_flags = 'LEFT,RIGHT,GAZE,HREF,RAW,AREA,HTARGET,GAZERES,BUTTON,STATUS,INPUT'
        link_sample_flags = 'LEFT,RIGHT,GAZE,GAZERES,PUPIL,HREF,AREA,HTARGET,STATUS,INPUT'
        
        self.tk.sendCommand("file_event_filter = %s" % file_event_flags)
        self.tk.sendCommand("file_sample_data = %s" % file_sample_flags)
        self.tk.sendCommand("link_event_filter = %s" % link_event_flags)
        self.tk.sendCommand("link_sample_data = %s" % link_sample_flags)

        # Pass screen resolution  to the tracker
        self.tk.sendCommand(f"screen_pixel_coords = 0 0 {self.mon_size[0]-1} {self.mon_size[1]-1}")

        # Send a DISPLAY_COORDS message so Data Viewer knows the correct screen size
        self.tk.sendMessage(f"DISPLAY_COORDS = 0 0 {self.mon_size[0]-1} {self.mon_size[1]-1}")

        # Choose a calibration type, H3, HV3, HV5, HV13 (HV = horizontal/vertical)
        self.tk.sendCommand(f"calibration_type = {self.calibration_type }")

        self.tk.sendCommand("calibration_area_proportion = 0.80 0.78")
        self.tk.sendCommand("validation_area_proportion = 0.80 0.78")

    def calibrate(self):
        calib_prompt = 'You will see dots on the screen, please gaze at them'
        calib_msg = visual.TextStim(self.win, text=calib_prompt, color='white', units='pix')
        calib_msg.draw()
        self.win.flip()

        pylink.closeGraphics()
        graphics = EyeLinkCoreGraphicsPsychoPy(self.tk, self.win)
        pylink.openGraphicsEx(graphics)

        # Calibrate the tracker
        self.tk.doTrackerSetup()
        self.calibrated = True
        prompt = 'Calibration finished'
        prompt_msg = visual.TextStim(self.win, text=prompt, color='Black', units='pix')
        prompt_msg.draw()
        self.win.flip()
        
        
    def start(self, filename="TEST.EDF"):
        self.filename = filename        
        print(f"-new_filename-:{self.streamName}:{op.split(filename)[-1]}")
        self.fname_temp = "name8chr.edf"
        self.tk.openDataFile(self.fname_temp)
        # self.outlet = StreamOutlet(self.stream_info)
        self.streaming = True

        pylink.beginRealTimeMode(100)
        self.tk.startRecording(1, 1, 1, 1)
        print("Eyetracker recording")
        self.recording = True
        self.stream_thread = threading.Thread(target=self.record)
        self.stream_thread.start()

    def record(self):

        print("Eyetracker LSL recording")
        self.paused = False
        old_sample = None
        values = []
        while self.recording:
            if self.paused:
                time.sleep(.1)
                continue

            smp = self.tk.getNewestSample()

            if smp is not None and old_sample != smp:
                    
                ppd = smp.getPPD()
                timestamp = smp.getTime()
                values = [0, 0, 0, 0, 0, 0, smp.getTargetX(), smp.getTargetY(), smp.getTargetDistance(),
                          ppd[0], ppd[1], timestamp]

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

            time.sleep(.0005)

        self.tk.stopRecording()
        self.tk.closeDataFile()

    def stop(self):
        self.recording = False
        if self.streaming:
            self.stream_thread.join()
            print("Eyelink stoped recording, downaloading edf")
            self.tk.receiveDataFile(self.fname_temp, self.filename)
            self.streaming = False

    def close(self):
        if self.recording:
            self.stop()
        self.tk.close()
