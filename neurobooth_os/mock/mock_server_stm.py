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
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient
from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, get_fprint
from neurobooth_os.tasks.task_importer import get_task_funcs
from neurobooth_os.iout import metadator as meta



def run_task(task_funct, s2, lsl_cmd, subj_id, task, task_karg={}):
    """Runs a task

    Parameters
    ----------
    task_funct : callable
        Task to run
    s2 : object
        socket object for connecting local to ctr
    lsl_cmd : str
        command to send though s2.
    subj_id : str
        name of the subject
    task : str
        name of the task
    task_karg : dict, optional
        Kwarg to pass to task_funct, by default {}

    Returns
    -------
    res : callable
        Task object
    """
    resp = socket_message(f"record_start:{subj_id}_{task}", "dummy_acq", wait_data=3)
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

def mock_stm_routine(host, port, conn):
    """ Mocks the tasks performed by STM server

    Parameters
    ----------
    host : str
        host ip of the server
    port : int
        port the server to listen
    conn : object
        connector to the database
    """

    def print_funct(msg=None):
        if msg is not None:
            print("Mock STM:::", msg)
    fprint_flush = print_funct
    
    streams = {}
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for data, connx in get_client_messages(s1, fprint_flush, sys.stdout, port=port, host=host):

        if "prepare" in data:
            # data = "prepare:collection_id:str(tech_obs_log_dict)"

            collection_id = data.split(":")[1]
            tech_obs_log = eval(data.replace(f"prepare:{collection_id}:", ""))

            task_func_dict = get_task_funcs(collection_id, conn)

            if len(streams):
                fprint_flush("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("presentation", collection_id, conn=conn)
                fprint_flush()
                fprint_flush("Preparing devices")

            fprint_flush("UPDATOR:-Connect-")

        elif "present" in data:   
            #-> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3
            tasks = data.split(":")[1].split("-")
            subj_id = data.split(":")[2]

            for task in tasks:
                host_ctr, _ = node_info("control")
                tech_obs_log_id = meta._make_new_tech_obs_row(conn, subj_id)

                task_karg ={"path": config.paths['data_out'],
                            "subj_id": subj_id,
                            "marker_outlet": streams['marker'],
                            "event_marker": streams['marker']}

                if task in task_func_dict.keys():
                    fprint_flush(f"Initiating task:{task}:{tech_obs_log_id}")

                    tsk_fun = task_func_dict[task]
                    res = run_task(tsk_fun, s2, subj_id, task, fprint_flush, task_karg)

                    fprint_flush(f"Finished task:{task}")

                else:
                    fprint_flush(f"Task not {task} implemented")

        elif data in ["close", "shutdown"]:
            streams = close_streams(streams)
            fprint_flush("Closing devices")

            if "shutdown" in data:                
                fprint_flush("Closing Stim server")
                break

        elif "time_test" in data:
            msg = f"ping_{time.time()}"
            connx.send(msg.encode("ascii"))

        else:
            fprint_flush(data)
