from psychopy import sound, visual, monitors, core, event






class Timing_Test():
    def  __init__(self, win=None, event_marker=None):
        SCN_W, SCN_H = (1920, 1080)
        monitor_width = 55
        monitor_distance = 50
        full_screen = True

        customMon = monitors.Monitor('demoMon', width=monitor_width, distance=monitor_distance)
        if win is None:
            win = visual.Window((SCN_W, SCN_H), fullscr=full_screen,
                            monitor=customMon, units='pix')
        target = visual.Rect(win, size=[1920, 1080], fillColor='white')


        # if event_marker is None:
        #     event_marker = marker_stream()

        win.setMouseVisible(False)
        inx = 0

        for _ in range(10):
            mySound = sound.Sound(1000, 0.1)
            target.draw()
            core.wait(1)
            win.flip()
            mySound.play()
            # event_marker.push_sample(['1'])
            core.wait(1)
            win.color = (0, 0, 0)
            win.flip()


            # keys = event.getKeys(keyList=['escape'])
            # if keys:
            #     win.setMouseVisible(True)
            #     # win.close()
            #     # core.quit()
            # inx += 1

            # if inx > 300:
            #     print("Finished timing task")
            #     break
        # win.close()
        # core.quit()


