# -*- coding: utf-8 -*-
"""
Created on Fri Aug 13 15:07:20 2021

@author: CTR
"""

import math


def deg2pix(visual_angle, cmdist, pixpercm):
    cmsize = math.tan(math.radians(visual_angle)) * float(cmdist)
    pixels = cmsize * pixpercm
    return pixels


def pix2deg(pixels, cmdist, pixpercm):
    cmsize = pixels / pixpercm
    deg = math.degrees(math.atan(cmsize / cmdist))
    return deg


def peak_vel2freq(peak_vel, amplitude_deg):
    # max_vel: sets the peak velocity of the target
    # phase: sets start position of target
    # angular_freq: each full cycle (left to right, right to left is 1/freq_x)
    # pos(t) = amplitude ⋅ sin(2πft)
    # vel(t) = d(pos(t))/dt = amplitude*cos(2πft)*2πf
    # peak_vel = amplitude * 2πf (max value of cos is 1)
    # f = peak_vel / 2π*amplitude
    freq = peak_vel / (2 * math.pi * amplitude_deg)
    return freq
