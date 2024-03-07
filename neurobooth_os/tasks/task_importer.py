# -*- coding: utf-8 -*-
"""

"""
import os.path as op
from typing import Dict, Any

import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg
from neurobooth_os.iout.stim_param_reader import TaskArgs, InstructionArgs


def get_task_funcs(collection_id):
    """Retrieves callable task objects, parameters and info from yaml files using collection_id

    Parameters
    ----------
    collection_id : str
        name of the collection from database

    Returns
    -------
    dict with task objects, task_id, task arguments
        dict containing key task name and value callable task
    """

    task_ids = meta.get_task_ids_for_collection(collection_id)
    task_args: Dict[str, TaskArgs] = meta.build_tasks_for_collection(collection_id)


    task_func_dict = {}
    for task_id in task_ids:
        # task_stim_id, task_dev, task_sens, instr_kwargs = meta.get_task_param(
        #    task_id, conn
        # )  # xtask_sens -> sens_id, always end with id
        task = task_args[task_id]
        task_stim_id = task.stim_args.stimulus_id
        if task.instr_args is not None:
            instr_args: InstructionArgs = task.instr_args
            if instr_args.instruction_file is not None:
                instr_args.instruction_file = op.join(
                    cfg.neurobooth_config.video_task_dir, instr_args.instruction_file
                )
        instr_kwargs = dict(task.instr_args)
        stim_file, stim_kwargs = meta.get_stimulus_kwargs_from_file(task_stim_id)
        task_kwargs: Dict[str:Any] = {**stim_kwargs, **instr_kwargs}

        # Convert path to class to class inst.
        stim_func = meta.str_fileid_to_eval(stim_file)

        task_func_dict[task_stim_id] = {}
        task_func_dict[task_stim_id]["obj"] = stim_func
        task_func_dict[task_stim_id]["t_obs_id"] = task_id
        task_func_dict[task_stim_id]["kwargs"] = task_kwargs

    return task_func_dict
