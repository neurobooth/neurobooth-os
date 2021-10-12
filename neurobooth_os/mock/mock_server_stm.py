# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""

import time
from time import sleep
import socket
import sys
from collections import OrderedDict

from neurobooth_os import config
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams, connect_mbient
from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, get_fprint
from neurobooth_os.tasks.task_importer import get_task_funcs
from neurobooth_os.iout import metadator as meta



def run_task(task_funct,subj_id, task, print, task_karg={}):
    """Runs a task

    Parameters
    ----------
    task_funct : callable
        Task to run
    subj_id : str
        name of the subject
    task : str
        name of the task
    print : callable
        print function
    task_karg : dict, optional
        Kwarg to pass to task_funct, by default {}

    Returns
    -------
    res : callable
        Task object
    """
    res = task_funct(**task_karg) 
    resp = socket_message(f"record_start:{subj_id}_{task}", "dummy_acq", wait_data=3)
    print(resp)
    sleep(.5)
    res.run()
    socket_message("record_stop", "dummy_acq")
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
            msg = "Mock STM:::" + msg
            socket_message(msg, "dummy_ctr")
    # print = print_funct
    
    streams = {}
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for data, connx in get_client_messages(s1, print, sys.stdout, port=port, host=host):

        if "prepare" in data:
            # data = "prepare:collection_id:str(tech_obs_log_dict)"

            collection_id = data.split(":")[1]
            tech_obs_log = eval(data.replace(f"prepare:{collection_id}:", ""))

            task_func_dict = get_task_funcs(collection_id, conn)

            if len(streams):
                print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("dummy_stm", collection_id, conn=conn)
                print("Preparing devices")

            print("UPDATOR:-Connect-")

        elif "present" in data:   
            #-> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3
            tasks = data.split(":")[1].split("-")
            subj_id = data.split(":")[2]
            task_karg ={"path": config.paths['data_out'],
                        "subj_id": subj_id,
                        "marker_outlet": streams['marker'],
                        }
            for task in tasks:                
                if task in task_func_dict.keys():                    
                    obs_id = task_func_dict[task]['obs_id']
                    tech_obs_log_id = meta._make_new_tech_obs_row(conn, subj_id)
                    print(f"Initiating task:{task}:{obs_id}:{tech_obs_log_id}")
                    sleep(1)

                    # get task, params and run 
                    tsk_fun = task_func_dict[task]['obj']
                    this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}
                    res = run_task(tsk_fun, subj_id, task, print, this_task_kwargs)
                    print(f"Finished task:{task}")

                    # Log tech_obs to database
                    tech_obs_log["tech_obs_id"] = obs_id
                    tech_obs_log['event_array'] = "event:datestamp"
                    meta._fill_tech_obs_row(tech_obs_log_id, tech_obs_log, conn)
                    
                else:
                    print(f"Task {task} not implemented")

        elif data in ["close", "shutdown"]:
            streams = close_streams(streams)
            print("Closing devices")

            if "shutdown" in data:                
                print("Closing Stim server")
                break

        elif "time_test" in data:
            msg = f"ping_{time.time()}"
            connx.send(msg.encode("ascii"))

        else:
            print(data)
