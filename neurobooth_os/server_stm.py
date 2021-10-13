import socket
import io
import sys
import os
from collections import OrderedDict
from time import time, sleep

import pandas as pd

from neurobooth_os import config
from neurobooth_os.iout import ScreenMirror
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient

from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, NewStdout

from neurobooth_os.tasks.test_timing.audio_video_test import Timing_Test
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs

from neurobooth_os.iout import metadator as meta

# os.chdir(r'C:\neurobooth-eel\neurobooth_os\\')
print(os.getcwd())


def fake_task(**kwarg):
    sleep(10)


def run_task(task_funct,subj_id, task, print, task_karg={}):
    """Runs a task

    Parameters
    ----------
    task_funct : callable
        Task to run
    subj_id : str
        name of the subject
    task : str
        name of the task
    print : callable
        print function
    task_karg : dict, optional
        Kwarg to pass to task_funct, by default {}

    Returns
    -------
    res : callable
        Task object
    """

    resp = socket_message(f"record_start:{subj_id}_{task}", "acquisition", wait_data=3)
    print(resp)
    sleep(.5)
    res = task_funct(**task_karg) 
    res.run()
    socket_message("record_stop", "acquisition")
    return res


def Main():

    sys.stdout = NewStdout("STM",  target_node="control", terminal_print=False)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    win = utl.make_win(full_screen=False)
    streams, screen_running = {}, False

    for data, conn in get_client_messages(s1):

        if "scr_stream" in data:
            if not screen_running:
                screen_feed = ScreenMirror()
                screen_feed.start()
                print("Stim screen feed running")
                screen_running = True
            else:
                print(f"-OUTLETID-:Screen:{screen_feed.oulet_id}")
                print("Already running screen feed")

        elif "prepare" in data:
            # data = "prepare:collection_id:str(tech_obs_log_dict)"

            collection_id = data.split(":")[1]
            tech_obs_log = eval(data.replace(f"prepare:{collection_id}:", ""))

            task_func_dict = get_task_funcs(collection_id)

            if len(streams):
                print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("presentation", collection_id, win=win)               
                print("Preparing devices")

            print("UPDATOR:-Connect-")

        elif "present" in data:  # -> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3
            tasks = data.split(":")[1].split("-")
            subj_id = data.split(":")[2]
            task_karg ={"win": win,
                        "path": config.paths['data_out'],
                        "subj_id": subj_id,
                        "marker_outlet": streams['marker'],
                        }
            if streams.get('Eyelink'):
                    task_karg["eye_tracker"] = streams['Eyelink']
                
            win = welcome_screen(with_audio=True, win=win)
            for task in tasks:
                if task not in task_func_dict.keys():
                    print(f"Task {task} not implemented")
                    continue
                
                obs_id = task_func_dict[task]['obs_id']
                tech_obs_log_id = meta._make_new_tech_obs_row(conn, subj_id)
                print(f"Initiating task:{task}:{obs_id}:{tech_obs_log_id}")
                sleep(1)

                if task != "pursuit_task_1":
                    fname = f"{config.paths['data_out']}{subj_id}{task}.edf"
                    if streams.get('eye_tracker'):
                        streams['eye_tracker'].start(fname)
                            
                # get task, params and run 
                tsk_fun = task_func_dict[task]['obj']
                this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}
                res = run_task(tsk_fun, subj_id, task, print, this_task_kwargs)
                print(f"Finished task:{task}")

                # Log tech_obs to database
                tech_obs_log["tech_obs_id"] = obs_id
                tech_obs_log['event_array'] = "event:datestamp"
                meta._fill_tech_obs_row(tech_obs_log_id, tech_obs_log, conn)     
                
                if streams.get('Eyelink'):
                    streams['Eyelink'].stop()
            finish_screen(win)

        elif data in ["close", "shutdown"]:
            streams = close_streams(streams)
            print("Closing devices")

            if "shutdown" in data:
                if screen_running:
                    screen_feed.stop()
                    print("Closing screen mirroring")
                    screen_running = False
                print("Closing Stim server")
                break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            conn.send(msg.encode("ascii"))

        else:
            print(data)

    s1.close()
    sys.stdout = sys.stdout.terminal
    win.close()


Main()
