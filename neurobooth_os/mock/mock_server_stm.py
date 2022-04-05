# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""

import os
import time
from time import sleep
import socket
import sys
from collections import OrderedDict
from datetime import datetime

from neurobooth_os import config
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams
from neurobooth_os.netcomm import socket_message, get_client_messages, get_data_timeout
from neurobooth_os.tasks.task_importer import get_task_funcs
from neurobooth_os.iout import metadator as meta



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
    
    streams = {}
    s1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    for data, connx in get_client_messages(s1, port=port, host=host):

        if "prepare" in data:
            # data = "prepare:collection_id:str(log_task_dict)"

            collection_id = data.split(":")[1]
            log_task = eval(data.replace(f"prepare:{collection_id}:", ""))
            subject_id_date = log_task["subject_id-date"]

            ses_folder = os.path.join(config.paths['data_out'], subject_id_date)
            if not os.path.exists(ses_folder):
                os.mkdir(ses_folder)

            # delete subj_date as not present in DB
            del log_task["subject_id-date"]

            task_func_dict = get_task_funcs(collection_id, conn)
            task_devs_kw = meta._get_device_kwargs_by_task(collection_id, conn)
            
            if len(streams):
                print("Checking prepared devices")
                streams = reconnect_streams(streams)
            else:
                streams = start_lsl_threads("dummy_stm", collection_id, conn=conn)

            print("UPDATOR:-Connect-")

        elif "present" in data:   
            #-> "present:TASKNAME:subj_id"
            # task_name can be list of task1-task2-task3
            tasks, subj_id = data.split(":")[1:]
            task_karg ={"path": config.paths['data_out'],
                        "subj_id": subject_id_date,
                        "marker_outlet": streams['marker'],
                        }
            
            for task in tasks.split("-"):                
                if task not in task_func_dict.keys():
                    print(f"Task {task} not implemented")
                    continue

                # get task and params
                tsk_fun = task_func_dict[task]['obj']
                this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}
                
                # Do not record if intro instructions
                if "intro_" in task:
                    res = tsk_fun(**this_task_kwargs)
                    res.run(**this_task_kwargs)
                    continue                    
                
                t_obs_id = task_func_dict[task]['t_obs_id']
                log_task_id = meta._make_new_task_row(conn, subj_id)
                log_task["date_times"] = '{'+ datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '}'
                tsk_strt_time = datetime.now().strftime("%Hh-%Mm-%Ss")

                # Signal CTR to start LSL rec
                print(f"Initiating task:{task}:{t_obs_id}:{log_task_id}:{tsk_strt_time}")
                sleep(1)

                 # Start/Stop rec in ACQ and run task
                resp = socket_message(f"record_start::{subject_id_date}_{tsk_strt_time}_{t_obs_id}::{task}",
                                     "dummy_acq", wait_data=10)

                sleep(.5)
                events = None
                res = tsk_fun(**this_task_kwargs)
                if hasattr(res, 'run'):  events = res.run(**this_task_kwargs)
                
                socket_message("record_stop", "dummy_acq", wait_data=15)
                print(f"Finished task:{task}")
                
                # Log task to database
                log_task["task_id"] = t_obs_id
                log_task['event_array'] =  str(events).replace("'", '"') if events is not None else "event:datestamp"
                meta._fill_task_row(log_task_id, log_task, conn)
                
                # Check if pause requested, continue or stop
                data = get_data_timeout(s1, .1)
                if data == "pause tasks":
                    print("Session Paused")
                    
                    conn, _ = s1.accept()
                    data = conn.recv(1024)
                    data = data.decode("utf-8")
                    
                    if data == "continue tasks":
                        continue                    
                    elif data == "stop tasks":
                        break
                    elif data == 'calibrate':
                        print('No calibration task for mock')
                    else:
                        print("While paused received another message")

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
