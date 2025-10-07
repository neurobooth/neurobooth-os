from __future__ import division, absolute_import

import os
from typing import Union

import pylink
from psychopy import visual
from enum import Enum

from neurobooth_os.tasks import Task
from neurobooth_os.tasks.smooth_pursuit.utils import deg2pix


class EyelinkColor(Enum):
    """
       Color codes accepted by the Eyetracker.
       The source of these codes is from the comments in the examples
       provided by SR Research - specifically saccade.py
       Example script can be found in:
       C:\Program Files (x86)\SR Research\EyeLink\SampleExperiments\Python\examples\Psychopy_examples
    """
    BLACK = 0
    BLUE = 1
    GREEN = 2
    CYAN = 3
    RED = 4
    MAGENTA = 5
    BROWN = 6
    LIGHTGRAY = 7
    DARKGRAY = 8
    LIGHTBLUE = 9
    LIGHTGREEN = 10
    LIGHTCYAN = 11
    LIGHTRED = 12
    BRIGHTMAGENTA = 13
    YELLOW = 14
    BRIGHTWHITE = 15


class Task_Eyetracker(Task):
    """
    Task that uses an Eyetracker from SR Research for target-directed gaze routines where the subject's eyes
    are presented with a fixed or moving target.
    """
    def __init__(self, eye_tracker=None, target_size=7, **kwargs):
        super().__init__(**kwargs)

        self.eye_tracker = eye_tracker
        self.mon_size = self.win.monitor.getSizePix()
        self.SCN_W, self.SCN_H = self.mon_size
        self.monitor_width = self.win.monitor.getWidth()
        self.pixpercm = self.mon_size[0] / self.monitor_width
        self.subj_screendist_cm = self.win.monitor.getDistance()

        self.target_size_pix = self.deg_2_pix(target_size)

        # prepare the pursuit target, the clock and the movement parameters
        self.win.color = [0, 0, 0]
        self.win.flip()
        self.target = visual.GratingStim(
            self.win, tex=None, mask="circle", size=self.target_size_pix
        )

    def pos_psych2pix(self, locs: list):
        """compute location x, y from 0 centered psychopy to top-left centered pixels"""
        x = int(locs[0] + self.win.size[0] / 2.0)
        y = int(self.win.size[1] / 2.0 - locs[1])
        return [x, y]

    def send_target_loc(
            self, loc: list, target_name="target", to_marker=True, no_interpolation=0
    ):
        """send target loc(ation) 0 centered to eyetracker after converting to top-left centered pixels.
        no_interpolation: 0 or 1
            0 interpolates, 1 doesn't"""
        loc = self.pos_psych2pix(loc)
        self.sendMessage(
            f"!V TARGET_POS {target_name} {loc[0]}, {loc[1]} 1 {no_interpolation}",
            to_marker,
        )  # 1 0  eyetracker code x, y, draw (1 yes), interpolation (0 == yes)

    def deg_2_pix(self, deg):
        return deg2pix(deg, self.subj_screendist_cm, self.pixpercm)

    def sendMessage(self, msg, to_marker=True, add_event=False):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendMessage(msg)
            if to_marker:
                self.send_marker(msg, add_event)

    def setOfflineMode(self):
        if self.eye_tracker is not None:
            self.eye_tracker.paused = True
            self.eye_tracker.tk.setOfflineMode()

    def startRecording(self):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.startRecording(1, 1, 1, 1)
            self.eye_tracker.paused = False

    def sendCommand(self, msg):
        if self.eye_tracker is not None:
            self.eye_tracker.tk.sendCommand(msg)

    def doDriftCorrect(self, vals):
        # vals : int, position target in screen
        if self.eye_tracker is not None:
            self.eye_tracker.tk.doDriftCorrect(*vals)

    def gaze_contingency(self):
        # move task
        pass


class Eyelink_HostPC(Task_Eyetracker):
    '''
       Class containing methods that interact with the HostPC display.
       HostPC is the computer that controls the eye tracker camera. Tasks
       can interact with the display that is attached to this computer. In
       our set up, the display is an Android tablet running the Eyelink app.

       The commands that are sent to the HostPC are in the form of strings,
       the list of commands and documentation is available in the
       "COMMANDS.INI" file inside the HostPC (i.e. NUC) - this can be found
       via the WebUI or by browsing the filesystem in the NUC and looking in
       /elcl/exe directory. Additional documentation is in the SR Research
       forums.
    '''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def draw_cross(self, x: int, y: int, colour: EyelinkColor) -> None:
        '''Draw a cross at the x,y position on the screen of the specified colour
           x, y must be in the top-left centered coordinate space
        '''
        self.sendCommand('draw_cross %d %d %d' % (x, y, colour.value))

    def draw_box(self, x: int, y: int, width: int, height: int, colour: EyelinkColor, filled: bool = False) -> None:
        '''
           Draw a rectangle of size width by height (in pixels) around a point
           x,y on the screen. x, y must be in the top-left centered coordinate
           space.

           'draw_box' command for the HostPC takes in the diagonal coordinates and
           a color integer
        '''
        half_box_wid_in_pix = int(width/2)
        half_box_hei_in_pix = int(height/2)

        box_coords_top_x = x-half_box_wid_in_pix
        box_coords_top_y = y-half_box_hei_in_pix
        box_coords_bot_x = x+half_box_wid_in_pix
        box_coords_bot_y = y+half_box_hei_in_pix

        if not filled:
            self.sendCommand('draw_box %d %d %d %d %d' % (box_coords_top_x, box_coords_top_y,
                                                               box_coords_bot_x, box_coords_bot_y,
                                                               colour.value))
        else:
            self.sendCommand('draw_filled_box %d %d %d %d %d' % (box_coords_top_x, box_coords_top_y,
                                                               box_coords_bot_x, box_coords_bot_y,
                                                               colour.value))
            pass

    def update_screen(self, x: float, y: float) -> None:
        '''
           Draw a cross and a box on the eyelink tablet.
           x and y are positions in 0 centered psychopy coordinate space.
           x and y can be int or float
           See pos_psych2pix above
        '''

        # First clear tablet screen
        self.clear_screen()

        # convert from 0 centered to top-left centered coordinate space
        xy = self.pos_psych2pix([x, y])
        top_left_x = xy[0]
        top_left_y = xy[1]

        # draw cross at top_left centered x,y position
        self.draw_cross(top_left_x, top_left_y, EyelinkColor.LIGHTGREEN)

        # draw box around cross
        box_len_in_pix = 100
        self.draw_box(top_left_x, top_left_y, box_len_in_pix, box_len_in_pix, EyelinkColor.LIGHTRED)

    def clear_screen(self, colour: EyelinkColor = EyelinkColor.BLACK) -> None:
        """Clear the HostPC screen and leave a Black background by default"""
        self.sendCommand('clear_screen %d' % colour.value)

    def _render_image(self, path_to_image: Union[str, os.PathLike],
                     crop_x: int, crop_y: int, crop_width: int, crop_height: int,
                     host_x: int, host_y: int,
                     drawing_options: any = pylink.BX_MAXCONTRAST) -> None:
        """
           Employs the imageBackdrop method of eyetracker to display an image on
           HostPC screen. Documentation available as comments in (and code adapted
           from) picture.py example provided in SR Research software located at:
           C:\Program Files (x86)\SR Research\EyeLink\SampleExperiments\Python\examples\Psychopy_examples

           This method:
           ** DOES NOT SUPPORT IMAGE RESIZING **
           ** ONLY WORKS WHEN EYETRACKER IS IN OFFLINE MODE **

           Therefore this method needs to be executed before eyetracker starts
           recording

           :param path_to_image: complete file path to the image file
           :param crop_x/crop_y: x,y coordinate in pixels for cropping the image
           :param crop_width/crop_height: width and height in pixels  for cropping
                                          the image
           :param host_x/host_y: x,y position in pixels on the HostPC screen where
                                 the image needs to be rendered
           :param drawing_options: drawing options from SR Research's pylink package

           Example usage:
           If you want to render a 1920 by 1080 image on a 1920x1080 screen,
           crop_x/crop_y would be 0,0, since you do not want to crop anything
           crop_width/crop_height would be 1920/1080 since you want the full image
           host_x/host_y would be 0,0 since you want the full image displayed on
           screen

           For Bamboo Passage the image size is 1536 by 864 which we want to render
           on a 1920x1080 screen. We do not want to crop the image, but we want to
           center the image on screen. Therefore, the params would be:
           crop_x/crop_y = 0,0
           crop_width/crop_height = 1536, 864
           host_x/host_y = 192, 108 {i.e. (self.SCN_W-1536)/2 & (self.SCN_H-864)/2}

           This method ** DOES NOT SUPPORT ** image resizing. For resizing options
           follow the el_tracker.bitmapBackdrop() method provided in picture.py
           example script.

           This method starts with an '_'(underscore) because it is not meant to be
           called directly, and must be wrapped in a wrapper called 'render_image'
           within the task script for the image to be rendered when called within
           server_stm script.
        """
        self.clear_screen()

        if self.eye_tracker is not None:
            self.eye_tracker.tk.imageBackdrop(path_to_image,
                                           crop_x, crop_y, crop_width, crop_height,
                                           host_x, host_y,
                                           drawing_options)
