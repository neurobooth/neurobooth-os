from __future__ import absolute_import, division
import os.path as op
from psychopy import visual
from psychopy import prefs
prefs.hardware['audioLib']=['pyo']
from psychopy import sound, core, event
import time
import neurobooth_os.tasks.utils as utl



class Sit_to_Stand():
    def __init__(self, marker_outlet=None, win=None, **kwarg):
        
        self.fpath = op.dirname(op.abspath(__file__)).replace("\\", "/")
        
        if marker_outlet is not None:
            self.with_lsl = True
            self.marker = marker_outlet
            # self.marker.push_sample([f"Streaming_0_{time.time()}"])
        else:
            self.with_lsl = False

        if win is None:
            full_screen = False
            # Monitor resolution
            SCN_W, SCN_H = (1920, 1040)

            # Setup the Window
            self.win = visual.Window(
                size=(SCN_W, SCN_H), fullscr=full_screen, screen=1,
                winType='pyglet', allowGUI=False, allowStencil=False,
                monitor='testMonitor', color=[0,0,0], colorSpace='rgb',
                blendMode='avg', useFBO=True,
                units='height')
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

        welcome = visual.ImageStim(self.win, image=self.fpath + '/NB1.jpg', units='pix')
        welcome_audio = sound.Sound(self.fpath + '/welcome.wav', secs=-1, stereo=True, hamming=True,
            name='sustainph_audio_instructions')

        text='For this task, you will do sit-to-stand five times, as quickly as possible\n\nYou will be presented with the instruction video next\n\nPress any button to continue'
        instructions = utl.create_text_screen(self.win, text)
        instructions_audio = sound.Sound(self.fpath + '/instructions.wav', secs=-1, stereo=True, hamming=True)
        instruction_video = visual.MovieStim3(win=self.win, filename=self.fpath + '/instructions.mp4', noAudio=True)

        text='Please practice sit-to-stand one time'
        practice = utl.create_text_screen(self.win, text)
        practice_audio = sound.Sound(self.fpath + '/practice.wav', secs=-1, stereo=True, hamming=True)

        text='Please do sit-to-stand five times, as quickly as possible'
        task = utl.create_text_screen(self.win, text)
        task_audio = sound.Sound(self.fpath + '/task.wav', secs=-1, stereo=True, hamming=True)

        text='Thank you. You have completed this task'
        end = utl.create_text_screen(self.win, text)
        end_audio = sound.Sound(self.fpath + '/end.wav', secs=-1, stereo=True, hamming=True)


        # utl.present(self.win, welcome, welcome_audio, 10)
        self.send_marker("Intructions-start_0")
        
        utl.present(self.win, instructions, instructions_audio, 12)
        utl.play_video(self.win, instruction_video)
        self.send_marker("Intructions-end_1")

        self.send_marker("Practice-start_0")
        utl.present(self.win, practice, practice_audio, 3)
        self.send_marker("Practice-end_1")

        self.send_marker("Task-start_0")
        utl.present(self.win, task, task_audio, 5)
        self.send_marker("Task-end_0")

        utl.present(self.win, end, end_audio, 2)

        # Close win if just created for the task
        if self.win_temp:
            self.win.close()


if __name__ == "__main__" :

    sts = Sit_to_Stand()










