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

from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, get_fprint

from neurobooth_os.tasks.test_timing.audio_video_test import Timing_Test
from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs

from neurobooth_os.iout import metadator as meta

os.chdir(r'C:\neurobooth-eel\neurobooth_os\\')
print(os.getcwd())


def fake_task(**kwarg):
    sleep(10)


def run_task(
        task_funct,
        s2,
        lsl_cmd,
        subj_id,
        task,
        send_stdout,
        task_karg={}):
    resp = socket_message(
        f"record_start:{subj_id}_{task}", "acquisition", wait_data=3)
    print(resp)
    s2.sendall(lsl_cmd.encode('utf-8'))
    sleep(.5)
    s2.sendall(b"select all\n")
    sleep(.5)
    s2.sendall(b"start\n")  # LabRecorder start cmd
    sleep(.5)
    res = task_funct(**task_karg)
    s2.sendall(b"stop\n")
    socket_message("record_stop", "acquisition")
    sleep(2)
    return res


def Main():

    fprint_flush, old_stdout = get_fprint("STM")
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    win = utl.make_win(full_screen=False)
    streams, screen_running = {}, False

    for data in get_client_messages(s1, fprint, old_stdout):

        if "scr_stream" in data:
            if not screen_running:
                screen_feed = ScreenMirror()
                screen_feed.start()
                fprint_flush("Stim screen feed running")
                screen_running = True
            else:
                fprint_flush(f"-OUTLETID-:Screen:{screen_feed.oulet_id}")
                fprint_flush("Already running screen feed")

        elif "prepare" in data:
            # data = "prepare:collection_id:str(tech_obs_log_dict)"

            collection_id = data.split(":")[1]
            tech_obs_log = eval(data.replace(f"prepare:{collection_id}:", ""))

            task_func_dict = get_task_funcs(collection_id)

            if len(streams):
                fprint_flush("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads(
                    "presentation", collection_id, win=win)
                fprint_flush()
                streams['mouse'].start()
                if 'eye_tracker' in streams.keys():
                    streams['eye_tracker'].win = win
                fprint_flush("Preparing devices")

            fprint_flush("UPDATOR:-Connect-")

        elif "present" in data:  # -> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3
            tasks = data.split(":")[1].split("-")

            subj_id = data.split(":")[2]

            win = welcome_screen(with_audio=True, win=win)

            # Connection to LabRecorder in ctr pc
            host_ctr, _ = node_info("control")
            s2 = socket.create_connection((host_ctr, 22345))

            for task in tasks:
                host_ctr, _ = node_info("control")
                tech_obs_log_id = meta.make_new_tech_obs_id()

                # Generates filename command for LabRecorder
                lsl_cmd = ("filename {root:" + config.paths['data_out'] + "}"
                           "{template:%p_%b.xdf}"
                           "{participant:" + subj_id +
                           "_" + tech_obs_log_id + "_} "
                           "{task:" + task + "}\n")

                task_karg = {"win": win,
                             "path": config.paths['data_out'],
                             "subj_id": subj_id,
                             "marker_outlet": streams['marker'],
                             "event_marker": streams['marker']}

                if streams.get('Eyelink'):
                    task_karg["eye_tracker"] = streams['Eyelink']

                if task in task_func_dict.keys():
                    tsk_fun = task_func_dict[task]
                    # c.send(msg.encode("ascii"))
                    fprint_flush(f"Initiating task: {task}:{tech_obs_log_id}")

                    if task != "pursuit_task_1":
                        fname = f"{config.paths['data_out']}{subj_id}{task}.edf"
                        if streams.get('eye_tracker'):
                            streams['eye_tracker'].start(fname)

                    res = run_task(tsk_fun, s2, lsl_cmd, subj_id,
                                   task, fprint_flush, task_karg)
                    if streams.get('Eyelink'):
                        streams['Eyelink'].stop()

                    fprint_flush(f"Finished task: {task}")
                    if streams.get('Eyelink'):
                        del streams['Eyelink']

                else:
                    fprint_flush(f"Task not {task} implemented")

            finish_screen(win)

        elif data in ["close", "shutdown"]:
            streams = close_streams(streams)
            fprint_flush("Closing devices")

            if "shutdown" in data:
                if screen_running:
                    screen_feed.stop()
                    fprint_flush("Closing screen mirroring")
                    screen_running = False
                fprint_flush("Closing Stim server")
                break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            c.send(msg.encode("ascii"))
        elif "connect_mbient" in data:

            mbient = connect_mbient()

        else:
            fprint_flush(data)

    s1.close()
    sys.stdout = old_stdout
    win.close()


Main()
