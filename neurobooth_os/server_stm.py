import logging
import socket
import sys
import os
from time import time
from datetime import datetime
import copy
from collections import OrderedDict  # NOT an unused import, very naughtily used by an eval
from concurrent.futures import ThreadPoolExecutor, wait

from psychopy import prefs

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

import neurobooth_os
from neurobooth_os import config

# from neurobooth_os.iout.screen_capture import ScreenMirror
from neurobooth_os.iout.lsl_streamer import DeviceManager
from neurobooth_os.iout import metadator as meta
from neurobooth_os.iout.mbient import Mbient

from neurobooth_os.netcomm import (
    socket_message,
    get_client_messages,
    NewStdout,
    get_data_timeout,
)

from neurobooth_os.tasks.wellcome_finish_screens import welcome_screen, finish_screen
import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs
from neurobooth_os.log_manager import SystemResourceLogger, make_db_logger

def main():
    config.load_config()  # Load Neurobooth-OS configuration
    logger = make_db_logger()  # Initialize logging to default
    try:
        logger.debug("Starting STM")
        os.chdir(neurobooth_os.__path__[0])
        sys.stdout = NewStdout("STM", target_node="control", terminal_print=True)
        run_stm(logger)
        logger.debug("Stopping STM")
    except Exception as e:
        logger.critical(f"An uncaught exception occurred. Exiting: {repr(e)}")
        logger.critical(e, exc_info=sys.exc_info())
        logger.critical("Stopping STM (error-state)")
        raise
    finally:
        logging.shutdown()

def run_stm(logger):
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if os.getenv("NB_FULLSCREEN") == "false":
        win = utl.make_win(full_screen=False)
    else:
        win = utl.make_win(full_screen=True)

    screen_running, presented = False, False
    port = config.neurobooth_config['presentation']["port"]
    host = ''
    device_manager = None
    system_resource_logger = None

    for data, connx in get_client_messages(s1, port, host):
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
            logger.info("Preparing STM for operation.")
            collection_id = data.split(":")[1]
            database_name = data.split(":")[2]
            log_task = eval(
                data.replace(f"prepare:{collection_id}:{database_name}:", "")
            )
            subject_id: str = log_task["subject_id"]
            session_name = log_task["subject_id-date"]
            conn = meta.get_conn(database=database_name)
            logger.info(f"Database name is {database_name}.")
            ses_folder = f"{config.neurobooth_config['presentation']['local_data_dir']}{session_name}"

            logger.info(f"Creating session folder: {ses_folder}")
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            logger.info("Creating db logger initialized for the session.")
            logger = make_db_logger(subject_id, session_name)
            logger.info('LOGGER CREATED')

            if system_resource_logger is None:
                system_resource_logger = SystemResourceLogger(ses_folder, 'STM')
                system_resource_logger.start()

            # delete subj_date as not present in DB
            del log_task["subject_id-date"]

            task_func_dict = get_task_funcs(collection_id, conn)
            task_devs_kw = meta.get_device_kwargs_by_task(collection_id, conn)

            device_manager = DeviceManager(node_name='presentation')
            if device_manager.streams:
                print("Checking prepared devices")
                device_manager.reconnect_streams()
            else:
                device_manager.create_streams(collection_id=collection_id, win=win, conn=conn)
            eyelink_stream = device_manager.get_eyelink_stream()
            print("UPDATOR:-Connect-")

        elif "present" in data:  # -> "present:TASKNAME:subj_id:session_id"
            # task_name can be list of tk1-task2-task3

            logger.info("Beginning Presentation")
            tasks, subj_id, session_id = data.split(":")[1:]
            log_task["log_session_id"] = session_id

            # Shared task keyword arguments
            task_karg = {
                "win": win,
                "path": config.neurobooth_config['presentation']["local_data_dir"] + f"{session_name}/",
                "subj_id": session_name,
                "marker_outlet": device_manager.streams["marker"],
                "prompt": True,
            }

            # Pass device streams as keyword arguments if needed.
            # TODO: This needs to be cleaned up and not hard-coded
            if eyelink_stream is not None:  # For eye tracker tasks
                task_karg["eye_tracker"] = eyelink_stream
            task_karg['mbients'] = device_manager.get_mbient_streams()  # For the mbient reset task

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
                meta.log_task_params(conn, task, log_task_id, task_func_dict[task]["kwargs"])
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

                with ThreadPoolExecutor(max_workers=1) as executor:
                    # Start recording on ACQ in parallel to starting on STM
                    logger.info(f'SENDING record_start TO ACQ')
                    acq_result = executor.submit(
                        socket_message,
                        f"record_start::{session_name}_{tsk_strt_time}_{t_obs_id}::{task}",
                        "acquisition",
                        wait_data=10,
                    )

                    # Start eyetracker if device in task
                    if eyelink_stream is not None and any("Eyelink" in d for d in list(task_devs_kw[task])):
                        fname = f"{task_karg['path']}/{session_name}_{tsk_strt_time}_{t_obs_id}.edf"
                        if "calibration_task" in task:  # if not calibration record with start method
                            this_task_kwargs.update({"fname": fname, "instructions": calib_instructions})
                        else:
                            eyelink_stream.start(fname)

                    device_manager.mbient_reconnect()  # Attempt to reconnect Mbients if disconnected

                    wait([acq_result])  # Wait for ACQ to finish
                    acq_result.result()  # Raise any exceptions swallowed by the executor

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

                with ThreadPoolExecutor(max_workers=1) as executor:
                    # Stop recording on ACQ in parallel to stopping on STM
                    logger.info(f'SENDING record_stop TO ACQ')
                    acq_result = executor.submit(socket_message, "record_stop", "acquisition", wait_data=15)

                    # Stop eyetracker
                    if eyelink_stream is not None and any("Eyelink" in d for d in list(task_devs_kw[task])):
                        if "calibration_task" not in task:
                            eyelink_stream.stop()

                    wait([acq_result])  # Wait for ACQ to finish
                    acq_result.result()  # Raise any exceptions swallowed by the executor

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
                log_task["task_notes_file"] = f"{session_name}-{task}-notes.txt"

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

        elif "shutdown" in data:
            if system_resource_logger is not None:
                system_resource_logger.stop()

            logger.info("Shutting down")
            win.close()
            sys.stdout = sys.stdout.terminal
            s1.close()
            if device_manager is not None:
                device_manager.close_streams()
            break

        elif "time_test" in data:
            msg = f"ping_{time()}"
            connx.send(msg.encode("ascii"))

        else:
            logger.error(f'Unexpected message received: {data}')

    exit()


if __name__ == '__main__':
    main()
