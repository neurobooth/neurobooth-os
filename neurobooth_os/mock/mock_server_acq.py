# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""
import os
import time
import socket
from collections import OrderedDict

from neurobooth_os import config
from neurobooth_os.iout.lsl_streamer import (
    start_lsl_threads,
    close_streams,
    reconnect_streams,
)
from neurobooth_os.netcomm import get_client_messages

from neurobooth_os.iout import metadator as meta


def mock_acq_routine(host, port, conn):
    """Mocks the tasks performed by ACQ server

    Parameters
    ----------
    host : str
        host ip of the server.
    port : int
        port the server to listen.
    conn : object
        Connector to the database
    """

    config.load_config()
    streams = {}
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    recording = False
    for data, connx in get_client_messages(s1, port=port, host=host):

        if "prepare" in data:
            # data = "prepare:collection_id:database:str(log_task_dict)"
            collection_id = data.split(":")[1]
            database_name = data.split(":")[2]
            log_task = eval(data.replace(f"prepare:{collection_id}:{database_name}:", ""))
            subject_id_date = log_task["subject_id-date"]
            ses_folder = f"{config.neurobooth_config['acquisition']['local_data_dir']}{subject_id_date}"
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)
            if len(streams):
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("dummy_acq", collection_id, conn=conn)

            devs = list(streams.keys())
            print("UPDATOR:-Connect-")

        elif "frame_preview" in data and not recording:
            if not any("IPhone" in s for s in streams):
                msg = "ERROR: no iphone in LSL streams"
                print(msg)
                connx.send(msg.encode("utf-8"))
                continue

            frame = streams[[i for i in streams if "IPhone" in i][0]].frame_preview()
            frame_prefix = b"::BYTES::" + str(len(frame)).encode("utf-8") + b"::"
            frame = frame_prefix + frame
            connx.send(frame)

        elif "record_start" in data:
            # -> "record_start::FILENAME" FILENAME = {subj_id}_{task}

            print("Starting recording")
            filename, task = data.split("::")[1:]
            fname = os.path.join(config.neurobooth_config["acquisition"]["local_data_dir"], filename)
            for k in streams.keys():
                if any([i in k for i in ["hiFeed", "Intel", "FLIR", "IPhone"]]):
                    if task_devs_kw[task].get(k):
                        streams[k].start(fname)
            msg = "ACQ_devices_ready"
            connx.send(msg.encode("ascii"))
            recording = True

        elif "record_stop" in data:
            print("Closing recording")
            for k in streams.keys():
                if any([i in k for i in ["hiFeed", "Intel", "FLIR", "IPhone"]]):
                    streams[k].stop()
            msg = "ACQ_devices_stoped"
            connx.send(msg.encode("ascii"))
            recording = False

        elif data in ["close", "shutdown"]:
            print("Closing devices")
            streams = close_streams(streams)

            if "shutdown" in data:
                print("Closing RTD cam")
                break

        elif "time_test" in data:
            msg = f"ping_{time.time()}"
            connx.send(msg.encode("ascii"))

        else:
            print(data)
