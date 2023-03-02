import socket
import sys
import os
from time import time
from datetime import datetime
import copy
from typing import NamedTuple, Dict, Any

# This import SEEMS unused, but is used by the eval statement in prepare()
from collections import OrderedDict

from psychopy import prefs
from psychopy.visual import Window

prefs.hardware["audioLib"] = ["PTB"]
prefs.hardware["audioLatencyMode"] = 3

import neurobooth_os
from neurobooth_os import config

from neurobooth_os.iout.lsl_streamer import DeviceStreamManagerSTM
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


def Main():
    os.chdir(neurobooth_os.__path__[0])

    set_stdout()
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    if os.getenv("NB_FULLSCREEN") == "false":
        win = utl.make_win(full_screen=False)
    else:
        win = utl.make_win(full_screen=True)

    # The following variables are global server state shared across successive messages
    device_streams = DeviceStreamManagerSTM()
    screen_feed = ScreenFeed()
    presented = False
    prepare_data = None

    # Infinite loop - process incoming messages
    for data, connx in get_client_messages(s1):
        # print(f'Message received: {data}')

        if "scr_stream" in data:
            screen_feed.start()
        elif "prepare" in data:
            prepare_data = prepare(device_streams, data)
        elif "present" in data:
            present(device_streams, prepare_data, s1, win, presented, data)
            presented = True
        elif data == "close":
            device_streams.close()
        elif data == "shutdown":
            win.close()
            sys.stdout = sys.stdout.terminal
            s1.close()
            device_streams.close()
            screen_feed.stop()
            break  # Exit infinite message loop
        elif "time_test" in data:
            connx.send(f"ping_{time()}".encode("ascii"))
        else:
            print(f'Unexpected message: {data}')


def set_stdout() -> None:
    sys.stdout = NewStdout("STM", target_node="control", terminal_print=True)


class PrepareData(NamedTuple):
    log_task: Dict[str, str]
    task_func_dict: Dict[str, Any]
    subject_id_date: str
    collection_id: str
    db_connection: Any


def prepare(device_streams: DeviceStreamManagerSTM, message: str) -> PrepareData:
    # Parse message
    # format: "prepare:collection_id:database:str(log_task_dict)"
    # TODO: Standardize and move message logic; get rid of eval
    _, collection_id, database_name, *_ = message.split(':')
    log_task = eval(message.replace(f'prepare:{collection_id}:{database_name}:', ''))
    subject_id_date = log_task['subject_id-date']

    # delete subj_date as not present in DB
    del log_task["subject_id-date"]

    # Create session folder
    ses_folder = f"{config.paths['data_out']}{subject_id_date}"
    if not os.path.exists(ses_folder):
        os.mkdir(ses_folder)

    # Get task functions
    conn = meta.get_conn(database=database_name)
    task_func_dict = get_task_funcs(collection_id, conn)

    # Prepare device streams
    device_streams.prepare(collection_id, conn)

    print("UPDATOR:-Connect-")
    return PrepareData(
        log_task=log_task,
        task_func_dict=task_func_dict,
        subject_id_date=subject_id_date,
        collection_id=collection_id,
        db_connection=conn,
    )


def present(
        device_streams: DeviceStreamManagerSTM,
        prepare_data: PrepareData,
        s1: socket.socket,
        win: Window,
        presented: bool,
        message: str
) -> None:
    # Extract dictionaries from prepared data
    log_task = prepare_data.log_task
    task_func_dict = prepare_data.task_func_dict
    if presented:  # Refresh task functions if already presented
        task_func_dict = get_task_funcs(prepare_data.collection_id, prepare_data.db_connection)

    # Parse message
    # format: "present:TASKNAME:subj_id:session_id"
    # task_name can be list of task1-task2-task3
    _, tasks, subj_id, session_id = message.split(":")
    tasks = tasks.split("-")
    log_task["log_session_id"] = session_id

    # Construct task argument dictionary
    task_karg: Dict[str, Any] = {
        "win": win,
        "path": config.paths["data_out"] + f"{prepare_data.subject_id_date}/",
        "subj_id": prepare_data.subject_id_date,
        "marker_outlet": device_streams.get_streams_by_name('marker')[0],
        "prompt": True,
    }
    if device_streams.has_stream('Eyelink'):
        task_karg["eye_tracker"] = device_streams.get_streams_by_name('Eyelink')[0]

    # Preload tasks media
    for task in tasks:
        if task not in task_func_dict:
            continue
        task_fun = copy.copy(task_func_dict[task]["obj"])
        this_task_kwargs = {**task_karg, **task_func_dict[task]["kwargs"]}
        task_func_dict[task]["obj"] = task_fun(**this_task_kwargs)

    # Display welcome screen
    win = welcome_screen(win=win)
    if not hasattr(sys.stdout, "terminal"):  # When win is created, stdout pipe is reset
        set_stdout()

    task_calib = [t for t in tasks if "calibration_task" in t]
    # Show calibration instruction video only the first time
    calib_instructions = True

    while len(tasks):
        task = tasks.pop(0)
        t00 = time()

        if task not in task_func_dict.keys():
            print(f"Task {task} not implemented")
            continue

        # get task and params
        task_fun = task_func_dict[task]["obj"]
        this_task_kwargs = {**task_karg, **task_func_dict[task]["kwargs"]}
        t_obs_id = task_func_dict[task]["t_obs_id"]

        # Do not record if intro instructions
        if "intro_" in task or "pause_" in task:
            task_fun.run(**this_task_kwargs)
            continue

        log_task_id = meta._make_new_task_row(prepare_data.db_connection, subj_id)

        task_start_time = datetime.now()
        log_task["date_times"] = ("{" + task_start_time.strftime("%Y-%m-%d %H:%M:%S") + ",")
        task_start_time = task_start_time.strftime("%Hh-%Mm-%Ss")

        # Signal CTR to start LSL rec and wait for start confirmation
        t0 = time()
        print(f"Initiating task:{task}:{t_obs_id}:{log_task_id}:{task_start_time}")
        ctr_msg = None
        while ctr_msg != "lsl_recording":
            ctr_msg = get_data_timeout(s1, 4)
        print(f"Waiting for CTR took: {time() - t0}")

        # Start Eyelink if not calibration
        eyelink_filename = f"{task_karg['path']}/{prepare_data.subject_id_date}_{task_start_time}_{t_obs_id}.edf"
        device_streams.record_start_eyelink(task, eyelink_filename)
        if "calibration_task" in task:
            this_task_kwargs.update({'fname': eyelink_filename, 'instructions': calib_instructions})

        # Start rec in ACQ
        _ = socket_message(
            f"record_start::{prepare_data.subject_id_date}_{task_start_time}_{t_obs_id}::{task}",
            "acquisition",
            wait_data=True,
        )

        # Start mBients
        device_streams.record_start_mbients()

        if len(tasks) == 0:
            this_task_kwargs.update({"last_task": True})
        this_task_kwargs["task_name"] = t_obs_id
        this_task_kwargs["subj_id"] += "_" + task_start_time

        print(f"Total TASK WAIT start took: {time() - t00}")

        # Run task
        events = task_fun.run(**this_task_kwargs)

        # Stop rec in ACQ
        t0 = t00 = time()
        _ = socket_message("record_stop", "acquisition", wait_data=True)
        print(f"ACQ stop took: {time() - t0}")

        # Stop devices
        device_streams.record_stop_mbients()
        device_streams.record_stop_eyelink(task)

        # Signal CTR to start LSL rec and wait for start confirmation
        print(f"Finished task: {task}")

        # Log task to database
        log_task["date_times"] += (datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "}")
        log_task["task_id"] = t_obs_id
        log_task["event_array"] = (
            str(events).replace("'", '"')
            if events is not None
            else "event:datestamp"
        )
        log_task["task_notes_file"] = f"{prepare_data.subject_id_date}-{task}-notes.txt"

        if task_fun.task_files is not None:
            log_task["task_output_files"] = task_fun.task_files
        else:
            if log_task.get("task_output_files", "empty") != "empty":
                del log_task["task_output_files"]

        meta._fill_task_row(log_task_id, log_task, prepare_data.db_connection)

        print(f"Total TASK WAIT stop took: {time() - t00}")

        # Check if pause requested, unpause or stop
        data = get_data_timeout(s1, 0.1)
        if data == "pause tasks":
            pause_screen = utl.create_text_screen(win, text="Session Paused")
            utl.present(win, pause_screen, waitKeys=False)

            connx2, _ = s1.accept()
            data = connx2.recv(1024).decode("utf-8")

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

    finish_screen(win)


ENABLE_SCREEN_MIRROR = False
if ENABLE_SCREEN_MIRROR:
    from neurobooth_os.iout.screen_capture import ScreenMirror

    class ScreenFeed:
        running: bool
        feed: ScreenMirror = None

        def __init__(self):
            self.running = False

        def start(self) -> None:
            if not self.running:
                self.feed = ScreenMirror()
                self.feed.start()
                print("Stim screen feed running")
                self.running = True
            else:
                print(f"-OUTLETID-:Screen:{self.feed.outlet_id}")
                print("Already running screen feed")

        def stop(self) -> None:
            if self.running:
                self.feed.stop()
                self.running = False

else:
    class ScreenFeed:
        def start(self) -> None:
            print('Screen mirror not enabled!')

        def stop(self) -> None:
            pass


Main()
