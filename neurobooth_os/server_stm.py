import socket
import sys
import os
from time import time
from datetime import datetime
import copy
from collections import OrderedDict  # NOT an unused import, very naughtily used by an eval

from psychopy import prefs

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

import neurobooth_os
from neurobooth_os import config

# from neurobooth_os.iout.screen_capture import ScreenMirror
from neurobooth_os.iout.lsl_streamer import (
    start_lsl_threads,
    close_streams,
    reconnect_streams,
)
from neurobooth_os.iout import metadator as meta

from neurobooth_os.netcomm import (
    socket_message,
    get_client_messages,
    NewStdout,
    get_data_timeout,
)

from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs
from neurobooth_os.logging import make_session_logger, make_default_logger


def Main():
    os.chdir(neurobooth_os.__path__[0])
    sys.stdout = NewStdout("STM", target_node="control", terminal_print=True)

    # Initialize logging to default
    logger = make_default_logger()

    try:
        run_stm(logger)
    except Exception as e:
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        raise


def run_stm(logger):
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if os.getenv("NB_FULLSCREEN") == "false":
        win = utl.make_win(full_screen=False)
    else:
        win = utl.make_win(full_screen=True)

    streams, screen_running, presented = {}, False, False

    for data, connx in get_client_messages(s1):
        logger.info(f'MESSAGE RECEIVED: {data}')

        if "scr_stream" in data:
            pass
            # if not screen_running:
            #     screen_feed = ScreenMirror()
            #     screen_feed.start()
            #     print("Stim screen feed running")
            #     screen_running = True
            # else:
            #     print(f"-OUTLETID-:Screen:{screen_feed.outlet_id}")
            #     print("Already running screen feed")

        elif "prepare" in data:
            # data = "prepare:collection_id:database:str(log_task_dict)"

            collection_id = data.split(":")[1]
            database_name = data.split(":")[2]
            log_task = eval(
                data.replace(f"prepare:{collection_id}:{database_name}:", "")
            )
            subject_id_date = log_task["subject_id-date"]

            conn = meta.get_conn(database=database_name)
            ses_folder = f"{config.neurobooth_config['local_data_dir']}{subject_id_date}"
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            logger = make_session_logger(ses_folder, 'STM')
            logger.info('LOGGER CREATED')

            # delete subj_date as not present in DB
            del log_task["subject_id-date"]

            task_func_dict = get_task_funcs(collection_id, conn)
            task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)

            if len(streams):
                print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads(
                    "presentation", collection_id, win=win, conn=conn
                )

            print("UPDATOR:-Connect-")

        elif "present" in data:  # -> "present:TASKNAME:subj_id:session_id"
            # task_name can be list of task1-task2-task3

            tasks, subj_id, session_id = data.split(":")[1:]
            log_task["log_session_id"] = session_id

            task_karg = {
                "win": win,
                "path": config.neurobooth_config["local_data_dir"] + f"{subject_id_date}/",
                "subj_id": subject_id_date,
                "marker_outlet": streams["marker"],
                "prompt": True,
            }
            if streams.get("Eyelink"):
                task_karg["eye_tracker"] = streams["Eyelink"]

            if presented:
                task_func_dict = get_task_funcs(collection_id, conn)

            # Preload tasks media
            t0 = time()
            for task in tasks.split("-"):
                if task not in task_func_dict.keys():
                    continue
                tsk_fun = copy.copy(task_func_dict[task]["obj"])
                this_task_kwargs = {**task_karg, **task_func_dict[task]["kwargs"]}
                task_func_dict[task]["obj"] = tsk_fun(**this_task_kwargs)
            logger.debug(f'Task media took {time() - t0:.2f}')

            win = welcome_screen(win=win)
            # When win is created, stdout pipe is reset
            if not hasattr(sys.stdout, "terminal"):
                sys.stdout = NewStdout(
                    "STM", target_node="control", terminal_print=True
                )

            tasks = tasks.split("-")
            task_calib = [t for t in tasks if "calibration_task" in t]
            # Show calibration instruction video only the first time
            calib_instructions = True

            while len(tasks):
                task = tasks.pop(0)
                logger.info(f'TASK: {task}')

                if task not in task_func_dict.keys():
                    print(f"Task {task} not implemented")
                    logger.warning(f'Task {task} not implemented')
                    continue

                t0 = t00 = time()
                # get task and params
                tsk_fun = task_func_dict[task]["obj"]
                this_task_kwargs = {**task_karg, **task_func_dict[task]["kwargs"]}
                t_obs_id = task_func_dict[task]["t_obs_id"]
                # Do not record if intro instructions"
                if "intro_" in task or "pause_" in task:
                    logger.debug(f"RUNNING PAUSE/INTRO (No Recording)")
                    tsk_fun.run(**this_task_kwargs)
                    logger.debug(f"TASK FUNCTION RETURNED")
                    continue

                log_task_id = meta._make_new_task_row(conn, subj_id)
                log_task["date_times"] = (
                    "{" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + ","
                )
                tsk_strt_time = datetime.now().strftime("%Hh-%Mm-%Ss")

                # Signal CTR to start LSL rec and wait for start confirmation
                logger.info(f'STARTING TASK: {task}')
                t0 = time()
                print(f"Initiating task:{task}:{t_obs_id}:{log_task_id}:{tsk_strt_time}")
                logger.info(f'Initiating task:{task}:{t_obs_id}:{log_task_id}:{tsk_strt_time}')
                ctr_msg = None
                while ctr_msg != "lsl_recording":
                    ctr_msg = get_data_timeout(s1, 4)
                elapsed_time = time() - t0
                print(f"Waiting for CTR took: {elapsed_time:.2f}")
                logger.info(f'Waiting for CTR took: {elapsed_time:.2f}')

                # Start eyetracker if device in task
                if streams.get("Eyelink") and any(
                    "Eyelink" in d for d in list(task_devs_kw[task])
                ):
                    fname = f"{task_karg['path']}/{subject_id_date}_{tsk_strt_time}_{t_obs_id}.edf"

                    # if not calibration record with start method
                    if "calibration_task" in task:
                        this_task_kwargs.update(
                            {"fname": fname, "instructions": calib_instructions}
                        )
                    else:
                        streams["Eyelink"].start(fname)

                # Start rec in ACQ and run task
                logger.info(f'SENDING record_start TO ACQ')
                _ = socket_message(
                    f"record_start::{subject_id_date}_{tsk_strt_time}_{t_obs_id}::{task}",
                    "acquisition",
                    wait_data=10,
                )

                # mbient check connectin and start streaming
                for k in streams.keys():
                    if "Mbient" in k:
                        try:
                            if not streams[k].device.is_connected:
                                streams[k].try_reconnect()
                        except Exception as e:
                            print(e)
                            pass

                if len(tasks) == 0:
                    this_task_kwargs.update({"last_task": True})
                this_task_kwargs["task_name"] = t_obs_id
                this_task_kwargs["subj_id"] += "_" + tsk_strt_time

                elapsed_time = time() - t00
                print(f"Total TASK WAIT start took: {elapsed_time:.2f}")
                logger.info(f"Total TASK WAIT start took: {elapsed_time:.2f}")

                logger.debug(f"RUNNING TASK FUNCTION")
                events = tsk_fun.run(**this_task_kwargs)
                logger.debug(f"TASK FUNCTION RETURNED")

                # Stop rec in ACQ
                t0 = t00 = time()
                logger.info(f'SENDING record_stop TO ACQ')
                _ = socket_message("record_stop", "acquisition", wait_data=15)
                elapsed_time = time() - t0
                print(f"ACQ stop took: {elapsed_time:.2f}")
                logger.info(f"ACQ stop took: {elapsed_time:.2f}")
                # mbient stop streaming
                for k in streams.keys():
                    if "Mbient" in k:
                        streams[k].lsl_push = False

                # Stop eyetracker
                if streams.get("Eyelink") and any(
                    "Eyelink" in d for d in list(task_devs_kw[task])
                ):
                    if "calibration_task" not in task:
                        streams["Eyelink"].stop()

                # Signal CTR to start LSL rec and wait for start confirmation
                print(f"Finished task: {task}")
                logger.info(f'FINISHED TASK: {task}')

                # Log task to database
                log_task["date_times"] += (
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "}"
                )
                log_task["task_id"] = t_obs_id
                log_task["event_array"] = (
                    str(events).replace("'", '"')
                    if events is not None
                    else "event:datestamp"
                )
                log_task["task_notes_file"] = f"{subject_id_date}-{task}-notes.txt"

                if tsk_fun.task_files is not None:
                    log_task["task_output_files"] = tsk_fun.task_files
                else:
                    if log_task.get("task_output_files", "empty") != "empty":
                        del log_task["task_output_files"]

                meta._fill_task_row(log_task_id, log_task, conn)

                elapsed_time = time() - t00
                print(f"Total TASK WAIT stop took: {elapsed_time:.2f}")
                logger.info(f"Total TASK WAIT stop took: {elapsed_time:.2f}")

                # Check if pause requested, unpause or stop
                data = get_data_timeout(s1, 0.1)
                if data == "pause tasks":
                    logger.info('Session Paused')
                    pause_screen = utl.create_text_screen(win, text="Session Paused")
                    utl.present(win, pause_screen, waitKeys=False)

                    connx2, _ = s1.accept()
                    data = connx2.recv(1024)
                    data = data.decode("utf-8")
                    logger.info(f'PAUSE MESSAGE RECEIVED: {data}')

                    if data == "continue tasks":
                        continue
                    elif data == "stop tasks":
                        break
                    elif data == "calibrate":
                        if not len(task_calib):
                            print("No calibration task")
                            continue
                        tasks.insert(0, task_calib[0])
                        calib_instructions = False
                        print("Calibration task added")
                    else:
                        print("While paused received another message")

            logger.info('FINISH SCREEN')
            finish_screen(win)
            presented = True

        elif data in ["close", "shutdown"]:
            if "shutdown" in data:
                win.close()
                sys.stdout = sys.stdout.terminal
                s1.close()

            streams = close_streams(streams)

            if "shutdown" in data:
                # if screen_running:
                #     screen_feed.stop()
                #     screen_running = False
                break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            connx.send(msg.encode("ascii"))

        else:
            print(data)

    exit()


Main()
