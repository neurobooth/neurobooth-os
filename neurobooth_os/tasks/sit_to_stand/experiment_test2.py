# -*- coding: utf-8 -*-
"""
Created on Tue Sep  7 16:08:03 2021

@author: STM
"""

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


path_instruction_video=r"\\STM\neurobooth-eel\neurobooth_os\tasks\video_instructions\Videos_to_present\motor_Sit to Stand _2021_09_02_v0.5.mp4"

full_screen = False
win = make_win(full_screen)


instruction_video = visual.MovieStim3(win=win, filename=path_instruction_video, noAudio=False)
text='Please do sit-to-stand five times, as quickly as possible'
task = utl.create_text_screen(win, text)


text='Thank you. You have completed this task'
end = utl.create_text_screen(win, text)
end_audio = sound.Sound('end.wav', secs=-1, stereo=True, hamming=True)


while True:
    

    
    instruction_video.seek(0)
    utl.play_video(win, instruction_video)        
    
    text='Please press:\n\tContinue to practice sit-to-stand 5 times' +\
        "\n\tRepeat to view instructions again"            
    prepractice = utl.create_text_screen(win, text)
    prepractice.draw()
    win.flip()
    
    key = event.waitKeys(keyList=['space', 'r'])
    if key == ["space"]:
        instruction_video.stop()
        break
    elif key == ['r']:
        win.color = [0, 0, 0]
        win.flip()

            

      
utl.present(win, task, audio=None, wait_time=5)
 

utl.present(win, end, end_audio, 2)

win.close()


# if __name__ == "__main__" :

#     sts = Sit_to_Stand()
#     # print(sys.argv[1])
#     # time.sleep(10)
#     # print("DDDDDDDDDDDDDOOOONEEE")
#     # if len(sys.argv[1]) >1:
#     #     print(sys.argv[1])
#     #     time.sleep(10)
#     #     sts = Sit_to_Stand(path_instruction_video=sys.argv[1])
                                                          
                                                          
                                                          










