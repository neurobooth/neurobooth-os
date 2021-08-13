#!/usr/bin/env python3
#
# Description:
# A simple smooth pursuit task implemented in PsychoPy

import pylink
import os
import random
import config
from psychopy import visual, core, event, monitors
from tasks.smooth_pursuit.EyeLinkCoreGraphicsPsychoPy import EyeLinkCoreGraphicsPsychoPy
from math import sin, pi
import threading
from utils import deg2pix, peak_vel2freq

dummy_mode = False
SCN_W, SCN_H = (1920, 1080)


filename=  'pursuit.edf'
filename = config.paths['data_out'] + filename





class pursuit():
    
    def __init__(self, subj_id, eye_tracker, marker_outlet=None, win=None, monitor_width = 55, cmdist=75, amplitude_deg=30, peak_velocity_deg=33.3,  **kwarg):
        self.subj_id = subj_id
        self.filename = f"{subj_id}_pursuit.edf"  
        self.et = eye_tracker
        # self.filename = eye_tracker.fname_temp
        self.win = win
        
        self.mon_size = eye_tracker.mon_size
        self.tk = eye_tracker.tk
        self.monitor_width = monitor_width
        self.pixpercm = self.mon_size[0]/self.monitor_width
        self.cmdist = cmdist
        self.amplitude_deg = amplitude_deg
        self.peak_velocity_deg = peak_velocity_deg
        self.amplitude_pixel = deg2pix(self.amplitude_deg, self.cmdist, self.pixpercm)
        self.angular_freq = peak_vel2freq(self.peak_velocity_deg, self.peak_velocity_deg)

        # self.tk.openDataFile('pursuit.edf')
        # Add preamble text (file header)
        # self.tk.setOfflineMode()
        # self.tk.sendCommand("add_file_preamble_text 'Smooth pursuit task'")
        
        if not eye_tracker.calibrated:
            eye_tracker.calibrate()
            
        self.task_setup()
        
        self.et.start(self.filename)
        self.run()
        # self.et.stop()
        
        
    def task_setup(self):
        # prepare the pursuit target, the clock and the movement parameters
        self.win.color = [0, 0, 0]
        self.win.flip()
        self.target = visual.GratingStim(self.win, tex=None, mask='circle', size=25)
        self.pursuitClock = core.Clock()
        
        # Parameters for the Sinusoidal movement pattern
        # [amp_x, amp_y, phase_x, phase_y, angular_freq_x, angular_freq_y]
        self.mov_pars = [
            
                [self.amplitude_pixel/2, 0, 0, 0, self.angular_freq , self.angular_freq],
                [self.amplitude_pixel/2, 0, 0, 0, self.angular_freq , self.angular_freq],
                [self.amplitude_pixel/2, 0, 0, 0, self.angular_freq , self.angular_freq],
                [self.amplitude_pixel/2, 0, 0, 0, self.angular_freq , self.angular_freq]
                
                ]


    def run(self):
        
        # Run a block of 2 trials, in random order
        test_list = self.mov_pars[:1]
        random.shuffle(test_list)
        for trial in test_list:
            self.run_trial(8.0, trial)
        
        # Step 8: Close the EDF data file and put the tracker in idle mode
        self.tk.setOfflineMode()  # put the tracker in Offline
        pylink.pumpDelay(100)  # wait for 100 ms 
        self.tk.closeDataFile()
        
        # Step 9: Download EDF file to a local folder ('edfData')
        msg = 'Thank you \n Downloading EDF'
        edf = visual.TextStim(self.win, text=msg, color='white')
        edf.draw()
        self.win.flip()
        
        # self.receiveEDF()
        # x = threading.Thread(target=self.receiveEDF, daemon=True)
        # x.start()

        msg = 'Starting next task'
        edf = visual.TextStim(self.win, text=msg, color='white')
        edf.draw()
        self.win.flip()
        
        
    def receiveEDF(self):
        if not os.path.exists(config.paths['data_out']):
            os.mkdir(config.paths['data_out'])
        self.tk.receiveDataFile('pursuit.edf', self.filename)     
        
        
    def run_trial(self, trial_duration, movement_pars):
        """ Run a smooth pursuit trial
    
        trial_duration: the duration of the pursuit movement
        movement_pars: [amp_x, amp_y, phase_x, phase_y, freq_x, freq_y]
        The following equation defines a sinusoidal movement pattern
        y(t) = amplitude * sin(2 * pi * frequency * t + phase)
        for circular or elliptic movements, the phase in x and y directions
        should be pi/2 (direction matters)."""
    
        # Parse the movement pattern parameters
        amp_x, amp_y, phase_x, phase_y, freq_x, freq_y = movement_pars
    
        # Take the tracker offline
        self.tk.setOfflineMode()
    
        # Send the standard "TRIALID" message to mark the start of a trial
        self.tk.sendMessage("TRIALID")
    
        # Record_status_message : show some info on the Host PC
        self.tk.sendCommand("record_status_message 'Pursuit task'")
    
        # Drift check/correction, params, x, y, draw_target, allow_setup
        tar_x = amp_x*sin(phase_x)
        tar_y = amp_y*sin(phase_y)
        self.target.pos = (tar_x, tar_y)
        self.target.draw()
        self.win.flip()
        self.tk.doDriftCorrect(int(tar_x + self.mon_size[0]/2.0),
                               int(self.mon_size[1]/2.0 - tar_y), 0, 1)
    
        # Put the tracker in idle mode before we start recording
        # tk.setOfflineMode()
        
        # Start recording
        # params: file_sample, file_event, link_sampe, link_event (1-yes, 0-no)
        self.tk.startRecording(1, 1, 1, 1)
    
        # Wait for 100 ms to cache some samples
        pylink.msecDelay(100)
    
        # Send a message to mark movement onset
        frame = 0
        while True:
            self.target.pos = (tar_x, tar_y)
            self.target.draw()
            self.win.flip()
            flip_time = core.getTime()
            frame += 1
            if frame == 1: 
                self.tk.sendMessage('Movement_onset')
                move_start = core.getTime()
            else:
                _x = int(tar_x + SCN_W/2.0)
                _y = int(SCN_H/2.0 - tar_y)
                tar_msg = f'!V TARGET_POS target {_x}, {_y} 1 0'
                self.tk.sendMessage(tar_msg)
    
            time_elapsed = flip_time - move_start
    
            # update the target position
            tar_x = amp_x*sin(2 * pi * freq_x * time_elapsed + phase_x)
            tar_y = amp_y*sin(2 * pi * freq_y * time_elapsed + phase_y)
    
            # break if the time elapsed exceeds the trial duration
            if time_elapsed > trial_duration:
                break
        
        # clear the window
        self.win.color = (0, 0, 0)
        self.win.flip()
    
        # Stop recording
        self.tk.stopRecording()
        # self.et.paused = True
    
        # Send trial variables to record in the EDF data file
        self.tk.sendMessage(f"!V TRIAL_VAR amp_x {amp_x:.2f}")
        self.tk.sendMessage(f"!V TRIAL_VAR amp_y {amp_y:.2f}")
        self.tk.sendMessage(f"!V TRIAL_VAR phase_x {phase_x:.2f}")
        pylink.pumpDelay(2)  # give the tracker a break
        self.tk.sendMessage(f"!V TRIAL_VAR phase_y {phase_y:.2f}")
        self.tk.sendMessage(f"!V TRIAL_VAR freq_x {freq_x:.2f}")
        self.tk.sendMessage(f"!V TRIAL_VAR freq_y {freq_y:.2f}")
        self.tk.sendMessage(f"!V TRIAL_VAR duration {trial_duration:.2f}")
    
        # Send a 'TRIAL_RESULT' message to mark the end of the trial
        self.tk.sendMessage('TRIAL_RESULT')


        

