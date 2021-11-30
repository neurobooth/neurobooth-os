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
from datetime import datetime

from neurobooth_os import config
from neurobooth_os.iout.lsl_streamer import start_lsl_threads, close_streams, reconnect_streams
from neurobooth_os.netcomm import socket_message, get_client_messages
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
            # data = "prepare:collection_id:str(tech_obs_log_dict)"

            collection_id = data.split(":")[1]
            tech_obs_log = eval(data.replace(f"prepare:{collection_id}:", ""))
            study_id_date = tech_obs_log["study_id-date"]

            # delete subj_date as not present in DB
            del tech_obs_log["study_id-date"]

            task_func_dict = get_task_funcs(collection_id, conn)
            task_devs_kw = meta._get_coll_dev_kwarg_tasks(collection_id, conn)

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
            tasks, subj_id = data.split(":")[1:]
            task_karg ={"path": config.paths['data_out'],
                        "subj_id": study_id_date,
                        "marker_outlet": streams['marker'],
                        }

            for task in tasks.split("-"):                
                if task not in task_func_dict.keys():
                    print(f"Task {task} not implemented")
                    continue
  
                # get task and params
                tsk_fun = task_func_dict[task]['obj']
                this_task_kwargs = {**task_karg, **task_func_dict[task]['kwargs']}
                
                # Do not record if calibration or intro instructions"
                if 'calibration_task' in task or "intro_" in task:
                      res = tsk_fun(**this_task_kwargs)
                      res.run(**this_task_kwargs)
                      continue                    
                
                t_obs_id = task_func_dict[task]['t_obs_id']
                tech_obs_log_id = meta._make_new_tech_obs_row(conn, subj_id)
                tech_obs_log["date_times"] = '{'+ datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '}'
                tsk_strt_time = datetime.now().strftime("%Hh_%Mm_%Ss")

                # Signal CTR to start LSL rec
                print(f"Initiating task:{task}:{t_obs_id}:{tech_obs_log_id}:{tsk_strt_time}")
                sleep(1)

                 # Start/Stop rec in ACQ and run task
                resp = socket_message(f"record_start:{study_id_date}_{tsk_strt_time}_{task}:{task}",
                                     "dummy_acq", wait_data=3)
                print(resp)
                sleep(.5)
                res = tsk_fun(**this_task_kwargs)
                if hasattr(res, 'run'):  res.run(**this_task_kwargs)
                socket_message("record_stop", "dummy_acq")

                print(f"Finished task:{task}")

                # Log tech_obs to database
                tech_obs_log["tech_obs_id"] = t_obs_id
                tech_obs_log['event_array'] = "event:datestamp"
                meta._fill_tech_obs_row(tech_obs_log_id, tech_obs_log, conn)

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
