import socket
import sys
import os
from time import time, sleep
from collections import OrderedDict
from datetime import datetime

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.iout.screen_capture import ScreenMirror
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient
from neurobooth_os.iout import metadator as meta

from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, NewStdout

from neurobooth_os.tasks.test_timing.audio_video_test import Timing_Test
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs





def Main():
    os.chdir(neurobooth_os.__path__[0])

    sys.stdout = NewStdout("STM",  target_node="control", terminal_print=True)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    win = utl.make_win(full_screen=False)
    conn = meta.get_conn()

    streams, screen_running = {}, False

    for data, connx in get_client_messages(s1):

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

            task_func_dict = get_task_funcs(collection_id, conn)
            task_devs_kw = meta._get_coll_dev_kwarg_tasks(collection_id, conn)

            if len(streams):
                print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("presentation", collection_id, win=win)               
                print("Preparing devices")

            print("UPDATOR:-Connect-")

        elif "present" in data:  # -> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3
            
            tasks, subj_id = data.split(":")[1:]
            task_karg ={"win": win,
                        "path": config.paths['data_out'],
                        "subj_id": subj_id,
                        "marker_outlet": streams['marker'],
                        }
            if streams.get('Eyelink'):
                    task_karg["eye_tracker"] = streams['Eyelink']
                
            win = welcome_screen(with_audio=True, win=win)
            # When win is created, stdout pipe is reset
            sys.stdout = NewStdout("STM",  target_node="control", terminal_print=True)
            
            for task in tasks.split("-"):
                if task not in task_func_dict.keys():
                    print(f"Task {task} not implemented")
                    continue
                
                t_obs_id = task_func_dict[task]['t_obs_id']
                tech_obs_log_id = meta._make_new_tech_obs_row(conn, subj_id)
                # Signal CTR to start LSL rec
                print(f"Initiating task:{task}:{t_obs_id}:{tech_obs_log_id}")
                sleep(1)

                # Start eyetracker if device in tech_obs 
                if streams.get('Eyelink') and \
                            any('Eyelink' in d for d in list(task_devs_kw[task])):
                    if not streams['Eyelink'].calibrated:
                        streams['Eyelink'].calibrate()
                    fname = f"{config.paths['data_out']}{subj_id}_{t_obs_id}.edf"
                    streams['Eyelink'].start(fname)
                            
                # get task and params
                tsk_fun = task_func_dict[task]['obj']
                this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}

                # Start/Stop rec in ACQ and run task
                resp = socket_message(f"record_start:{subj_id}_{t_obs_id}:{task}",
                                     "acquisition", wait_data=3)
                print(resp)
                sleep(.5)
                res = tsk_fun(**this_task_kwargs)
                if hasattr(res, 'run'):  res.run(**this_task_kwargs)
                socket_message("record_stop", "acquisition")

                print(f"Finished task:{task}")

                # Log tech_obs to database
                tech_obs_log["tech_obs_id"] = t_obs_id
                tech_obs_log['event_array'] = "event:datestamp" # TODO: res should be event arrays
                tech_obs_log["date_times"] = '{'+ datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '}'
                meta._fill_tech_obs_row(tech_obs_log_id, tech_obs_log, conn)     
                
                if streams.get('Eyelink') and \
                            any('Eyelink' in d for d in list(task_devs_kw[task])):
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
            connx.send(msg.encode("ascii"))

        else:
            print(data)

    s1.close()
    sys.stdout = sys.stdout.terminal
    win.close()


Main()
