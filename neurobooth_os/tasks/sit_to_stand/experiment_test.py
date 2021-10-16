from psychopy import sound, core, event, monitors, visual
import time


def run():

    win = visual.Window()
    file = r"\\STM\Users\STM\Dropbox (Partners HealthCare)\Neurobooth Videos for tasks\Videos_to_present\motor_Sit to Stand _2021_09_02_v0.5.mp4"
    mov = visual.MovieStim3(win=win, filename=file, noAudio=False)
    mov.play()
    while mov.status != visual.FINISHED:
        mov.draw()
        win.flip()
        if event.getKeys():
            mov.stop()
            break


if __name__ == "__main__" :
   
    
    run()
    print("DDDDDDDDDDDDDOOOONEEE")
    time.sleep(10)

                                                          
                                                          










