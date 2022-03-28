# -*- coding: utf-8 -*-
"""
Created on Tue Aug 10 10:33:10 2021

@author: STM
"""
import importlib
import os.path as op

import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg

def _str_fileid_to_eval(stim_file_str):
    """" Converts string path.to.module.py::function() to callable

    Parameters
    ----------
        stim_file_str: str
            string with path to py file :: and function()
            
    Returns
    -------
        task_func: callable
            callable of the function pointed by stim_file_str
    """
    
    strpars = stim_file_str.split(".py::")
    filepath = "neurobooth_os." + strpars[0]
    func = strpars[1].replace("()", "")

    task_module = importlib.import_module(filepath)
    task_func = getattr(task_module, func)
    return task_func


def get_task_funcs(collection_id, conn):
    """Retrieves callable task objects, parameters and infor from database using collection_id

    Parameters
    ----------
    collection_id : str
        name of the collection from database
    conn : object
        Connector to the database

    Returns
    -------
    dict with task objects, tech_obs_id, task arguments
        dict containing key task name and value callable task
    """

    tasks_obs = meta.get_tasks(collection_id, conn)

    task_func_dict = {}
    for obs_id in tasks_obs:        
        task_stim_id, task_dev, task_sens, instr_kwargs = meta._get_task_param(obs_id, conn)  # xtask_sens -> sens_id, always end with id
        if instr_kwargs.get('instruction_file') is not None:
            instr_kwargs['instruction_file'] =  op.join(cfg.paths['video_tasks'], instr_kwargs['instruction_file'])
        stim_file, stim_kwargs = meta._get_stimulus_kwargs(task_stim_id, conn)
        task_kwargs = {**stim_kwargs, **instr_kwargs}

        # Convert path to class to class inst.
        stim_func = _str_fileid_to_eval(stim_file)

        task_func_dict[task_stim_id] = {}
        task_func_dict[task_stim_id]['obj'] = stim_func
        task_func_dict[task_stim_id]['t_obs_id'] = obs_id
        task_func_dict[task_stim_id]['kwargs'] = task_kwargs

    return task_func_dict
