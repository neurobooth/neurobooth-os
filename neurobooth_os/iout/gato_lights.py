# -*- coding: utf-8 -*-
"""
Created on Wed Aug 18 14:46:18 2021

@author: STM
"""

import leglight

myLight_L = leglight.LegLight('192.168.137.230', 9123)
myLight_L.on()
myLight_L.color(5500)

myLight_R = leglight.LegLight('192.168.137.58', 9123)
myLight_R.on()
myLight_R.color(5500)


# allLights = leglight.discover(2)
# allLights.on()
# # >>> myLight.brightness(14)
# # >>> myLight.color(3500)
# # >>> myLight.off()

myLight_L.off()
myLight_R.off()
