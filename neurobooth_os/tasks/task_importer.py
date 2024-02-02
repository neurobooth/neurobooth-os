# -*- coding: utf-8 -*-
"""

"""
import importlib
import os.path as op
from typing import List, Dict, Any

import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg
from neurobooth_os.iout.stim_param_reader import TaskArgs


def str_fileid_to_eval(stim_file_str):
    """ Converts string path.to.module.py::function() to callable

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


# TODO(larry): replace calls to this function with validated version get_task_arguments()?
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
    dict with task objects, task_id, task arguments
        dict containing key task name and value callable task
    """

    tasks_obs = meta.get_task_ids_for_collection(collection_id, conn)

    task_func_dict = {}
    for task_id in tasks_obs:
        task_stim_id, task_dev, task_sens, instr_kwargs = meta.get_task_param(
            task_id, conn
        )  # xtask_sens -> sens_id, always end with id
        if instr_kwargs.get("instruction_file") is not None:
            instr_kwargs["instruction_file"] = op.join(
                cfg.neurobooth_config["video_tasks"], instr_kwargs["instruction_file"]
            )
        stim_file, stim_kwargs = meta.get_stimulus_kwargs_from_file(task_stim_id)
        task_kwargs: Dict[str:Any] = {**stim_kwargs, **instr_kwargs}

        # Convert path to class to class inst.
        stim_func = str_fileid_to_eval(stim_file)

        task_func_dict[task_stim_id] = {}
        task_func_dict[task_stim_id]["obj"] = stim_func
        task_func_dict[task_stim_id]["t_obs_id"] = task_id
        task_func_dict[task_stim_id]["kwargs"] = task_kwargs

    return task_func_dict


def get_task_arguments(collection_id, conn):
    """Retrieves TaskArgs objects from database using collection_id

    Parameters
    ----------
    collection_id : str
        name of the collection from database
    conn : object
        Connector to the database

    Returns
    -------
    dict of stimulus_id to TaskArgs object for every task in collection
    """

    task_ids: List[str] = meta.get_task_ids_for_collection(collection_id, conn)

    task_func_dict = {}
    for task_id in task_ids:
        task_args: TaskArgs = _get_task_arg(task_id, conn)
        task_stim_id = task_args.stim_args.stimulus_id
        task_func_dict[task_stim_id] = task_args
    return task_func_dict


def _get_task_arg(task_id: str, conn) -> TaskArgs:
    """Retrieves callable task object and related parameters from database

    Parameters
    ----------
    task_id : str
        name of the task from database
    conn : object
        Connector to the database

    Returns
    -------
    TaskArgs object
    """

    task_stim_id, task_dev, task_sens, instr_kwargs = meta.get_task_param(
        task_id, conn
    )  # xtask_sens -> sens_id, always end with id
    stim_file, stim_kwargs = meta.get_stimulus_kwargs_from_file(task_stim_id)

    # Get the parser needed for validation of contents
    arg_parser = stim_kwargs["arg_parser"]

    # Convert path class path to class inst.
    stim_func = str_fileid_to_eval(stim_file)
    parser_func = str_fileid_to_eval(arg_parser)
    parser = parser_func(**stim_kwargs)

    if instr_kwargs is not None:
        if instr_kwargs.instruction_file is not None:
            instr_kwargs.instruction_file = op.join(
                cfg.neurobooth_config["video_tasks"], instr_kwargs.instruction_file
            )
        task_args = TaskArgs(task_id=task_id,
                             task_constructor_callable=stim_func,
                             stim_args=parser,
                             instr_args=instr_kwargs)
    else:
        task_args = TaskArgs(task_id=task_id,
                             task_constructor_callable=stim_func,
                             stim_args=parser)
    return task_args
