from neurobooth_os.iout.eyelink_tracker import EyeTracker
from neurobooth_os.tasks import utils

win = utils.make_win(full_screen=False)
eye_tracker = EyeTracker(win=win)
eye_tracker.calibrate()
eye_tracker.start()
eye_tracker.stop()
eye_tracker.close()
win.close()