#!/usr/bin/env python3

from psychopy import visual, core, event, monitors
from math import sin, pi

full_screen = False
# Monitor resolution
SCN_W, SCN_H = (1920, 1080)
monitor_width = 35
monitor_distance = 65


# Step 4: # open a window for graphics and calibration
#
# Create a monitor object to store monitor information
customMon = monitors.Monitor('demoMon', width=monitor_width, distance=monitor_distance)

# Open a PsychoPy window
win = visual.Window((SCN_W, SCN_H), fullscr=full_screen,
                    monitor=customMon, units='pix')
# win = visual.Window(
#     size=(SCN_W, SCN_H), fullscr=full_screen, screen=0,
#     winType='pyglet', allowGUI=True, allowStencil=False,
#     monitor=customMon, color=[0,0,0], colorSpace='rgb',
#     blendMode='avg', useFBO=True, units='pix')


# Step 5: prepare the pursuit target, the clock and the movement parameters
instruction = visual.TextStim(
    win=win,
    name='instruct',
    text='Task: Follow the dot on the screen\n\n There will be 12 trials\n\n\n PRESS any KEY to START',
    font='Arial',
    pos=[
        0,
        0],
    height=50,
    wrapWidth=800,
    ori=0,
    color='white',
    colorSpace='rgb',
    opacity=1,
    languageStyle='LTR',
    depth=-1.0)

target = visual.GratingStim(win, tex=None, mask='circle', size=25)
fixation = visual.ShapeStim(win,
                            vertices=((0, -100), (0, 100), (0, 0), (-100, 0), (100, 0)),
                            lineWidth=5,
                            size=.2,
                            closeShape=False,
                            lineColor='white'
                            )
pursuitClock = core.Clock()

# Parameters for the Sinusoidal movement pattern
# [amp_x, amp_y, phase_x, phase_y, angular_freq_x, angular_freq_y]
mov_pars = [
    [8, 300, 300, pi * 3 / 2, 0, 1 / 8.0, 0],
    [8, 300, 300, pi / 2, 0, 0, 1 / 8.0],
    [8, 300, 300, pi * 3 / 2, 0, 1 / 4.0, 1 / 4.0],
    [8, 300, 300, pi / 2, 0, 1 / 4.0, 1 / 4.0],
    [8, 300, 300, pi * 3 / 2, 0, 1 / 2.0, 1 / 2.0],
    [8, 300, 300, pi / 2, 0, 1 / 2.0, 1 / 2.0],
    [16, 450, 450, pi * 3 / 2, 0, 1 / 8.0, 1 / 8.0],
    [16, 450, 450, pi / 2, 0, 1 / 8.0, 1 / 8.0],
    [16, 450, 450, pi * 3 / 2, 0, 1 / 4.0, 1 / 4.0],
    [16, 450, 450, pi / 2, 0, 1 / 4.0, 1 / 4.0],
    [16, 450, 450, pi * 3 / 2, 0, 1 / 2.0, 1 / 2.0],
    [16, 450, 450, pi / 2, 0, 1 / 2.0, 1 / 2.0]
]

instruction.draw()
win.flip()
event.waitKeys()
win.color = (0, 0, 0)
win.flip()


# Step 7: Run through a couple of trials
# define a function to group the code that will executed on each trial
def run_trial(movement_pars):
    """ Run a smooth pursuit trial

    trial_duration: the duration of the pursuit movement
    movement_pars: [amp_x, amp_y, phase_x, phase_y, freq_x, freq_y]
    The following equation defines a sinusoidal movement pattern
    y(t) = amplitude * sin(2 * pi * frequency * t + phase)
    for circular or elliptic movements, the phase in x and y directions
    should be pi/2 (direction matters)."""

    # Parse the movement pattern parameters
    trial_duration, amp_x, amp_y, phase_x, phase_y, freq_x, freq_y = movement_pars

    # Drift check/correction, params, x, y, draw_target, allow_setup
    tar_x = amp_x * sin(phase_x)
    tar_y = amp_y * sin(phase_y)
    target.pos = (tar_x, tar_y)
    target.draw()
    win.flip()

    # Send a message to mark movement onset
    frame = 0
    while True:
        target.pos = (tar_x, tar_y)
        target.draw()
        win.flip()
        flip_time = core.getTime()
        frame += 1
        if frame == 1:
            move_start = core.getTime()
        else:
            _x = int(tar_x + SCN_W / 2.0)
            _y = int(SCN_H / 2.0 - tar_y)
            tar_msg = f'!V TARGET_POS target {_x}, {_y} 1 0'

        time_elapsed = flip_time - move_start

        # update the target position
        tar_x = amp_x * sin(2 * pi * freq_x * time_elapsed + phase_x)
        tar_y = amp_y * sin(2 * pi * freq_y * time_elapsed + phase_y)

        # break if the time elapsed exceeds the trial duration
        if time_elapsed > trial_duration:
            break

    # clear the window
    win.color = (0, 0, 0)
    fixation.draw()
    win.flip()
    core.wait(5)
    win.color = (0, 0, 0)
    win.flip()


# Run a block of 2 trials, in random order
test_list = mov_pars[:]
# random.shuffle(test_list)
for trial in test_list:
    run_trial(trial)


win.close()
core.quit()
