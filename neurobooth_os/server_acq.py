import socket
import os
import sys
from time import time

# This import SEEMS unused, but is used by the eval statement in prepare()
from collections import OrderedDict

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.netcomm import NewStdout, get_client_messages
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import DeviceStreamManagerACQ
from neurobooth_os.iout import metadator as meta

def Main():
    os.chdir(neurobooth_os.__path__[0])

    sys.stdout = NewStdout("ACQ", target_node="control", terminal_print=True)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # The following variables are global server state shared across successive messages
    device_streams = DeviceStreamManagerACQ()
    low_feed = LowFeed()
    recording = False
    subject_id_date = None
    task = None

    # Infinite loop - process incoming messages
    for data, connx in get_client_messages(s1):
        # print(f'Message received: {data}')

        if "vis_stream" in data:
            low_feed.viz_stream()
        elif "prepare" in data:
            subject_id_date = prepare(device_streams, data)
        elif "frame_preview" in data and not recording:
            frame_preview(device_streams, connx)
        elif "record_start" in data:
            task = record_start(device_streams, subject_id_date, data, connx)
            recording = True
        elif "record_stop" in data:
            record_stop(device_streams, task, connx)
            recording = False
        elif "close" in data:
            device_streams.close()
        elif "shutdown" in data:
            sys.stdout = sys.stdout.terminal
            s1.close()
            device_streams.close()
            low_feed.close()
            break  # Exit infinite message loop
        elif "time_test" in data:
            connx.send(f"ping_{time()}".encode("ascii"))
        else:
            print(f'Unexpected message: {data}')


class LowFeed:
    stream: VidRec_Brio
    running: bool

    def __init__(self):
        self.running = False

    def viz_stream(self) -> None:
        if not self.running:
            self.stream = VidRec_Brio(
                camindex=config.paths['cam_inx_lowfeed'],
                doPreview=True,
            )
            self.running = True
            print("LowFeed running")
        else:
            print(f"-OUTLETID-:Webcam:{self.stream.preview_outlet_id}")
            print("Already running low feed video streaming")

    def close(self) -> None:
        if self.running:
            self.stream.close()
            self.running = False
            print("Closing RTD cam")


def prepare(device_streams: DeviceStreamManagerACQ, message: str) -> str:
    # Parse message
    # format: "prepare:collection_id:database:str(log_task_dict)"
    # TODO: Standardize and move message logic; get rid of eval
    _, collection_id, database_name, *_ = message.split(':')
    log_task = eval(message.replace(f'prepare:{collection_id}:{database_name}:', ''))
    subject_id_date = log_task['subject_id-date']

    # Create session folder
    ses_folder = f"{config.paths['data_out']}{subject_id_date}"
    if not os.path.exists(ses_folder):
        os.mkdir(ses_folder)

    # Prepare device streams
    conn = meta.get_conn(database=database_name)
    device_streams.prepare(collection_id, conn)

    print("UPDATOR:-Connect-")
    return subject_id_date


def frame_preview(device_streams: DeviceStreamManagerACQ, connx) -> None:
    streams = device_streams.get_streams_by_name('IPhone')
    if len(streams) == 0:
        print("no iPhone")
        connx.send("ERROR: No iPhone in LSL streams".encode("ascii"))
        return

    # Capture frame from iPhone and send to CTL
    frame = streams[0].frame_preview()
    frame_prefix = b"::BYTES::" + str(len(frame)).encode("utf-8") + b"::"
    frame = frame_prefix + frame
    connx.send(frame)


def record_start(device_streams: DeviceStreamManagerACQ, subject_id_date: str, message: str, connx) -> str:
    print("Starting recording")
    t0 = time()

    # Parse message
    # format: "record_start::filename::task_id" FILENAME = {subj_id}_{obs_id}
    # TODO: Standardize and move message logic
    _, file_name, task = message.split("::")
    file_name = f"{config.paths['data_out']}{subject_id_date}/{file_name}"

    device_streams.record_start_cameras(file_name, task)
    device_streams.record_start_mbients()

    print(f"Device start took {time() - t0:.2f}")
    connx.send("ACQ_devices_ready".encode("ascii"))
    return task


def record_stop(device_streams: DeviceStreamManagerACQ, task: str, connx) -> None:
    t0 = time()

    device_streams.record_stop_cameras(task)

    print(f"Device stop took {time() - t0:.2f}")
    connx.send("ACQ_devices_stoped".encode("ascii"))


Main()
