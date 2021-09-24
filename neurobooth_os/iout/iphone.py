import pyautogui

import time

position = pyautogui.position()


def click_iphone():
    pyautogui.click(x=3403, y=1204, button='left', clicks=3, interval=0.1)
    time.sleep(5)


click_iphone()

pyautogui.moveTo(position[0], position[1])
