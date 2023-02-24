import socket
import os
import sys
from typing import Dict, List, Any
from time import time

# This import SEEMS unused, but is used by the eval statement in prepare()
from collections import OrderedDict

import neurobooth_os
from neurobooth_os import config
from neurobooth_os.netcomm import NewStdout, get_client_messages
from neurobooth_os.iout.camera_brio import VidRec_Brio
from neurobooth_os.iout.lsl_streamer import (
    start_lsl_threads,
    close_streams,
    reconnect_streams,
)
import neurobooth_os.iout.metadator as meta


def Main():
    os.chdir(neurobooth_os.__path__[0])

    sys.stdout = NewStdout("ACQ", target_node="control", terminal_print=True)
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # The following variables are global server state shared across successive messages
    device_streams = DeviceStreams()
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


class DeviceStreams:
    # This class is very similar to the one in STM. Consider abstract base class. Downside: would make harder to follow.

    streams: Dict[str, Any]
    task_dev_kw: Dict[str, str]

    def __init__(self):
        self.streams = {}
        self.task_devs_kw = None

    def get_streams_by_name(self, name: str) -> List[Any]:
        return [stream for stream_name, stream in self.streams.items() if (name in stream_name)]

    def prepare(self, collection_id: str, database_name: str) -> None:
        conn = meta.get_conn(database=database_name)
        self.task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)
        if len(self.streams):
            # print("Checking prepared devices")
            self.streams = reconnect_streams(self.streams)
        else:
            # This will also start the Yeti and mBients
            self.streams = start_lsl_threads("acquisition", collection_id, conn=conn)

    def record_start_cameras(self, file_name: str, task: str) -> None:
        for name, stream in self.streams.items():
            if name.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                if self.task_devs_kw[task].get(name):
                    try:
                        stream.start(file_name)
                    except:
                        continue

    def record_start_mbients(self) -> None:
        for name, stream in self.streams.items():
            if "Mbient" in name:
                try:
                    if not stream.device.is_connected:
                        stream.try_reconnect()
                except Exception as e:
                    print(e)
                    pass

    def record_stop_cameras(self, task: str) -> None:
        for name, stream in self.streams.items():
            if name.split("_")[0] in ["hiFeed", "FLIR", "Intel", "IPhone"]:
                if self.task_devs_kw[task].get(name):
                    stream.stop()

    def close(self):
        self.streams = close_streams(self.streams)


def prepare(device_streams: DeviceStreams, message: str) -> str:
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
    device_streams.prepare(collection_id, database_name)

    print("UPDATOR:-Connect-")
    return subject_id_date


def frame_preview(device_streams: DeviceStreams, connx) -> None:
    steams = device_streams.get_streams_by_name('IPhone')
    if len(steams) == 0:
        print("no iPhone")
        connx.send("ERROR: No iPhone in LSL streams".encode("ascii"))
        return

    # Capture frame from iPhone and send to CTL
    frame = steams[0].frame_preview()
    frame_prefix = b"::BYTES::" + str(len(frame)).encode("utf-8") + b"::"
    frame = frame_prefix + frame
    connx.send(frame)


def record_start(device_streams: DeviceStreams, subject_id_date: str, message: str, connx) -> str:
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


def record_stop(device_streams: DeviceStreams, task: str, connx) -> None:
    t0 = time()

    device_streams.record_stop_cameras(task)

    print(f"Device stop took {time() - t0:.2f}")
    connx.send("ACQ_devices_stoped".encode("ascii"))


Main()
