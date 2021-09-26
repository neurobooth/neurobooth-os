# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""

import time
from time import sleep
import socket
import sys

from neurobooth_os import config
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams
from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, get_fprint
from neurobooth_os.tasks.task_importer import get_task_funcs
from neurobooth_os.iout import metadator as meta


def mock_acq_routine(host, port, conn):
    """ Mocks the tasks performed by ACQ server

    Parameters
    ----------
    host : str 
        host ip of the server.
    port : int
        port the server to listen.
    conn : object
        Connector to the database
    """
    def print_funct(msg):
        print("Mock STM:::", msg)
    fprint_flush = print_funct

    streams = {}
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    
    for data, connx in get_client_messages(s1, fprint_flush, sys.stdout, port=port, host=host):

        if "prepare" in data:
            # data = "prepare:collection_id:str(tech_obs_log_dict)"

            collection_id = data.split(":")[1]
            if len(streams):
                fprint_flush("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("acquisition", collection_id, conn)

            fprint_flush()
            devs = list(streams.keys())
            fprint_flush("UPDATOR:-Connect-")

        elif "dev_param_update" in data:
            pass

        elif "record_start" in data:  
        # -> "record_start:FILENAME" FILENAME = {subj_id}_{task}

            fprint_flush("Starting recording")
            fname = config.paths['data_out'] + data.split(":")[-1]
            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
                    streams[k].start(fname)
            msg = "ACQ_ready"
            connx.send(msg.encode("ascii"))
            fprint_flush("ready to record")

        elif "record_stop" in data:
            fprint_flush("Closing recording")
            for k in streams.keys():
                if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
                    streams[k].stop()
            fprint_flush()

        elif data in ["close", "shutdown"]:
            fprint_flush("Closing devices")
            streams = close_streams(streams)
            fprint_flush()

            if "shutdown" in data:               
                fprint_flush("Closing RTD cam")
                break

        elif "time_test" in data:
            msg = f"ping_{time.time()}"
            connx.send(msg.encode("ascii"))

        else:
            fprint_flush(data)


