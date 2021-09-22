from __future__ import absolute_import, division
import os
import os.path as op
from psychopy import visual
from psychopy import prefs
prefs.hardware['audioLib']=['pyo']
from psychopy import sound, core, event
import time
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.utils import make_win
import sys


class Sit_to_Stand():
    def __init__(self, path_instruction_video=r"\\STM\neurobooth-eel\neurobooth_os\tasks\video_instructions\Videos_to_present\motor_Sit to Stand _2021_09_02_v0.5.mp4", marker_outlet=None, win=None, **kwarg):
        
        self.fpath = op.dirname(op.abspath(__file__)).replace("\\", "/")
        self.pname_inst_vid = op.join(self.fpath, op.basename(path_instruction_video))
        self.pname_inst_vid = path_instruction_video
                
        print("path to instruction: ", self.pname_inst_vid)
        
        
        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
            # self.marker.push_sample([f"Streaming_0_{time.time()}"])
        else:
            self.with_lsl = False

        if win is None:
            full_screen = False

            # Setup the Window
            self.win = make_win(full_screen)
            self.win_temp = True
        else:
            self.win = win
            self.win_temp = False
            
        self.win.color = [0, 0, 0]
        self.win.flip()
        self.run()

    def send_marker(self, msg=None):
        # msg format str {word}_{value}
        if self.with_lsl:
            self.marker.push_sample([f"{msg}_{time.time()}"])

    def run(self):

        instruction_video = visual.MovieStim3(win=self.win, filename=self.pname_inst_vid, noAudio=False)
        

        # text='Please practice sit-to-stand one time'
        # practice = utl.create_text_screen(self.win, text)
        # practice_audio = sound.Sound(self.fpath + '/practice.wav', secs=-1, stereo=True, hamming=True)

        text='Please do sit-to-stand five times, as quickly as possible'
        task = utl.create_text_screen(self.win, text)
        # task_audio = sound.Sound(self.fpath + '/task.wav', secs=-1, stereo=True, hamming=True)

        text='Thank you. You have completed this task'
        end = utl.create_text_screen(self.win, text)
        end_audio = sound.Sound(self.fpath + '/end.wav', secs=-1, stereo=True, hamming=True)


        # utl.present(self.win, welcome, welcome_audio, 10)
        
        while True:
            self.send_marker("Intructions-start_0")
            utl.play_video(self.win, instruction_video, stop=False)        
            self.send_marker("Intructions-end_1")
            
            text='Please press:\n\tContinue to practice sit-to-stand 5 times' +\
                "\n\tRepeat to view instructions again"            
            prepractice = utl.create_text_screen(self.win, text)
            prepractice.draw()
            self.win.flip()
            
            key = event.waitKeys(keyList=['space', 'r'])
            if key == ["space"]:
                instruction_video.stop()
                break
            elif key == ['r']:                
                self.win.color = [0, 0, 0]
                self.win.flip()
                instruction_video.seek(0)
            

        self.send_marker("Task-start_0")
        utl.present(self.win, task, audio=None, wait_time=5)
        self.send_marker("Task-end_0")

        utl.present(self.win, end, end_audio, 2)

        # Close win if just created for the task
        if self.win_temp:
            self.win.close()


if __name__ == "__main__" :

    sts = Sit_to_Stand()
    # print(sys.argv[1])
    # time.sleep(10)
    # print("DDDDDDDDDDDDDOOOONEEE")
    # if len(sys.argv[1]) >1:
    #     print(sys.argv[1])
    #     time.sleep(10)
    #     sts = Sit_to_Stand(path_instruction_video=sys.argv[1])
                                                          
                                                          
                                                          










