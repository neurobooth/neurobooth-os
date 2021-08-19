import os
import numpy as np
import pylink
import psychopy
from psychopy import visual, core, event, monitors
import time
import uuid
from pylsl import StreamInfo, StreamOutlet
import threading
import neurobooth_os.config as config
from neurobooth_os.tasks.smooth_pursuit.EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy


class EyeTracker():

    def __init__(self, sample_rate=1000, monitor_width=55, monitor_distance=65, calibration_type="HV5",
                 win=None, with_lsl=True, ip='192.168.100.15'):
        self.IP = ip
        self.sample_rate = sample_rate
        self.monitor_width = monitor_width
        self.monitor_distance = monitor_distance
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
        self.stream_info = StreamInfo('EyeLink', 'Gaze', 20, self.sample_rate, 'float32', self.oulet_id)
        self.stream_info.desc().append_child_value("fps", str(self.sample_rate))
        # self.stream_info.desc().append_child_value("device_name", self.device_name)
        self.outlet = StreamOutlet(self.stream_info)
        print(f"-OUTLETID-:EyeLink:{self.oulet_id}")
        self.streaming = True
        self.calibrated = False
        self.recording = False
        self.paused = True
        self.connect_tracker()


    def connect_tracker(self):
        self.tk = pylink.EyeLink(self.IP)
        # # Open an EDF data file on the Host PC
        # self.tk.openDataFile('ev_test.edf')

        self.tk.setOfflineMode()
        pylink.msecDelay(50)
        self.tk.sendCommand(f'sample_rate {self.sample_rate}')

        # Make gaze, HREF, and raw (PUPIL) data available over the link
        sample_flag = 'LEFT,RIGHT,GAZE,GAZERES,PUPIL,HREF,AREA,STATUS,INPUT'
        self.tk.sendCommand(f'link_sample_data = {sample_flag}')

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
        self.fname_temp = "name8chr.edf"
        self.tk.openDataFile(self.fname_temp)
        # self.outlet = StreamOutlet(self.stream_info)
        self.streaming = True

        pylink.beginRealTimeMode(100)
        self.tk.startRecording(1,1,1,1)
        print("Eyetracker recording")
        self.recording = True
        self.stream_thread = threading.Thread(target=self.record)
        self.stream_thread.start()

    def record(self):
        import time
        print("Eyetracker LSL recording")
        self.paused = False
        old_sample = None
        values = []
        while self.recording:
            if self.paused:
                time.sleep(.1)
                print("eyetracker sleeping")
                continue
            
            smp = self.tk.getNewestSample()
            
            if old_sample == smp:
                print("same samples")
                print(values)
                
            if smp is not None and old_sample != smp:  
                
                # now = pylsl.local_clock()
                ppd = smp.getPPD()
                timestamp = smp.getTime()
                values = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                          smp.getTargetX(), smp.getTargetY(), smp.getTargetDistance(),
                          ppd[0], ppd[1], timestamp]
            
                # Grab gaze, HREF, raw, & pupil size data
                if smp.isRightSample():
                    gaze = smp.getRightEye().getGaze()
                    href = smp.getRightEye().getHREF()  # head ref not necessary
                    raw = smp.getRightEye().getRawPupil()  # raw not necessary
                    pupil = smp.getRightEye().getPupilSize() # pupil size
                    values[:7] = [p for pp in [gaze, href, raw] for p in pp] + [pupil]
                if smp.isLeftSample():
                    gaze = smp.getLeftEye().getGaze()
                    href = smp.getLeftEye().getHREF()
                    raw = smp.getLeftEye().getRawPupil()
                    pupil = smp.getLeftEye().getPupilSize()
                    values[7:14] = [p for pp in [gaze, href, raw] for p in pp] + [pupil]

                self.outlet.push_sample(values)
                old_sample = smp
                
            time.sleep(.001)
        
        self.tk.stopRecording()
        self.tk.closeDataFile()
        print(f"et stop {time.time()}")   
        
        
        # print(f"saving {self.fname_temp} EDF file to disk as {self.filename}")
        # self.tk.receiveDataFile(self.fname_temp, f'{config.paths["data_out"]}{self.filename}')
        # print("saving EDF file to disk DONE")

    def stop(self):
        self.recording = False
        print(f"stopping streaming {time.time()}")
        if self.streaming:
            
            t0 = time.time()
            self.stream_thread.join()
            print(f"join took {time.time() - t0}")
            print("Eyelink stoped recording, downaloading edf")
            t0 = time.time()
            self.tk.receiveDataFile(self.fname_temp, f'{config.paths["data_out"]}{self.filename}')
            print(f"took {time.time() - t0}")
            self.streaming = False

    def close(self):
       if self.recording == True:
           self.stop()
       self.tk.close()

# info = pylsl.stream_info("EyeLink", "Gaze", 9, 100, pylsl.cf_float32, "eyelink-" + socket.gethostname());
# outlet = pylsl.stream_outlet(info)
# while True:
#     try:
#         print
#         "Trying to connect to EyeLink tracker..."
#         try:
#             tracker = EyeLink("255.255.255.255")
#             print
#             "Established a passive connection with the eye tracker."
#         except:
#             tracker = EyeLink("100.1.1.1")
#             print
#             "Established a primary connection with the eye tracker."
#         beginRealTimeMode(100)
#         getEYELINK().startRecording(1, 1, 1, 1)
#         print
#         "Now reading samples..."
#         while True:
#             sample = getEYELINK().getNewestSample()
#             if sample is not None:
#                 now = pylsl.local_clock()
#                 ppd = sample.getPPD()
#                 values = [0, 0, 0, 0, sample.getTargetX(), sample.getTargetY(), sample.getTargetDistance(), ppd[0],
#                           ppd[1]]
#                 if (sample.isLeftSample()) or (sample.isBinocular()):
#                     values[0:2] = sample.getLeftEye().getGaze()
#                 if (sample.isRightSample()) or (sample.isBinocular()):
#                     values[2:4] = sample.getRightEye().getGaze()
#                 print
#                 values
#                 outlet.push_sample(pylsl.vectord(values), now, True)
#                 time.sleep(1.0 / 250)
#     except Exception, e:
#         print
#         "connection broke off: ", e


# smp = tk.getNewestSample()
# if smp is not None:
#     # Grab gaze, HREF, raw, & pupil size data
#     if smp.isRightSample():
#         gaze = smp.getRightEye().getGaze()
#         href = smp.getRightEye().getHREF()
#         raw = smp.getRightEye().getRawPupil()
#         pupil = smp.getRightEye().getPupilSize()
#     elif smp.isLeftSample():
#         gaze = smp.getLeftEye().getGaze()
#         href = smp.getLeftEye().getHREF()
#         raw = smp.getLeftEye().getRawPupil()
#         pupil = smp.getLeftEye().getPupilSize()
#
#     timestamp = smp.getTime()

# # Close the EDF data file on the Host
# tk.closeDataFile()
#
# # Download the EDF data file from Host
# tk.receiveDataFile('smp_test.edf', 'smp_test.edf')
#
# # Close the link to the tracker
# tk.close()
