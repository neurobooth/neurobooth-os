from __future__ import absolute_import, division
from psychopy import visual
from psychopy import prefs
prefs.hardware['audioLib']=['pyo']
from psychopy import sound, core, event


def create_text_screen(win, text):
    screen = visual.TextStim(win=win, name='',
                                   text=text,
                                   font='Open Sans',
                                   pos=(0, 0), height=0.05, wrapWidth=800, ori=0.0,
                                   color='white', colorSpace='rgb', opacity=None,
                                   languageStyle='LTR',
                                   depth=0.0)
    return screen



def present(win, screen, audio, wait_time):
    if screen is not None:
        screen.draw()
        win.flip()
    if audio is not None:
        audio.play()
    core.wait(wait_time)
    event.waitKeys()
    win.color = (0, 0, 0)
    win.flip()

def play_video(win, mov):
    mov.play()
    while mov.status != visual.FINISHED:
        mov.draw()
        win.flip()
        if event.getKeys():
            break



full_screen = False
# Monitor resolution
SCN_W, SCN_H = (1920, 1080)

# Setup the Window
win = visual.Window(
    size=(SCN_W, SCN_H), fullscr=full_screen, screen=1,
    winType='pyglet', allowGUI=False, allowStencil=False,
    monitor='testMonitor', color=[0,0,0], colorSpace='rgb',
    blendMode='avg', useFBO=True,
    units='height')




welcome = visual.ImageStim(win, image='NB1.jpg', units='pix')
welcome_audio = sound.Sound('welcome.wav', secs=-1, stereo=True, hamming=True,
    name='sustainph_audio_instructions')

text='For this task, you will do sit-to-stand five times, as quickly as possible\n\nYou will be presented with the instruction video next\n\nPress any button to continue'
instructions = create_text_screen(win, text)
instructions_audio = sound.Sound('instructions.wav', secs=-1, stereo=True, hamming=True)
instruction_video = visual.MovieStim3(win=win, filename='instructions.mp4', noAudio=True)

text='Please practice sit-to-stand one time'
practice = create_text_screen(win, text)
practice_audio = sound.Sound('practice.wav', secs=-1, stereo=True, hamming=True)

text='Please do sit-to-stand five times, as quickly as possible'
task = create_text_screen(win, text)
task_audio = sound.Sound('task.wav', secs=-1, stereo=True, hamming=True)

text='Thank you. You have completed this task'
end = create_text_screen(win, text)
end_audio = sound.Sound('end.wav', secs=-1, stereo=True, hamming=True)




present(win, welcome, welcome_audio, 10)
present(win, instructions, instructions_audio, 12)
play_video(win, instruction_video)

present(win, practice, practice_audio, 3)
present(win, task, task_audio, 5)
present(win, end, end_audio, 5)











