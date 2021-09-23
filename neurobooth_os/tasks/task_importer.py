# -*- coding: utf-8 -*-
"""
Created on Tue Aug 10 10:33:10 2021

@author: STM
"""
import importlib

import neurobooth_os.iout.metadator as meta


def str_fileid_to_eval(stim_file_str):
    """" Converts string path.to.module.py::function() to callable
    
    parameters:
        stim_file_str: str
            string with path to py file :: and function()
    returns:
        task_func: callable
            callable of the function pointed by stim_file_str
    """
    strpars = stim_file_str.split(".py::")
    filepath = "neurobooth_os." +strpars[0]
    func = strpars[1].replace("()","")
    
    task_module = importlib.import_module(filepath)
    task_func = getattr(task_module, func)
    return task_func




def get_task_funcs(collection_id):
    """" Using collection_id retrieves callable task objects
    
    parameters:
        collection_id: str
            name of the collection from DB
    returns:
        task_func_dict: dict
            dict containing key task name and value callable task
    """
    conn = meta.get_conn() 
    
    tasks = meta.get_tasks(collection_id, conn)
    
    task_func_dict = {}
    for task_id in tasks:
        task_stim_id, task_dev, task_sens = meta.get_task_param(task_id, conn)
        stim_file, param_file = meta.get_task_stim(task_stim_id, conn)
        stim_func = str_fileid_to_eval(stim_file)
        task_func_dict[task_stim_id] = stim_func
    
    conn.close()
    return task_func_dict



 