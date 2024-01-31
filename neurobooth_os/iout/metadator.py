# -*- coding: utf-8 -*-
import importlib
import logging
import os
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, Optional

from sshtunnel import SSHTunnelForwarder
import psycopg2
from neurobooth_terra import Table

import neurobooth_os.config as cfg
from neurobooth_os.iout import stim_param_reader
from neurobooth_os.iout.stim_param_reader import InstructionArgs, SensorArgs, get_cfg_path, DeviceArgs, StimulusArgs, \
    RawTaskParams, TaskArgs
from neurobooth_os.util.task_log_entry import TaskLogEntry, convert_to_array_literal


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


def get_conn(database, validate_config_paths: bool = True):
    """Gets connector to the database

    Parameters
    ----------
    database : str
        Name of the database
    validate_config_paths : bool, optional
        True if the config file path should be validated. This should generally be True outside test scenarios

    Returns
    -------
    conn : object
        connector to psycopg database
    """
    import neurobooth_os.log_manager as log_man

    logger = log_man.make_default_logger(log_level=logging.ERROR, validate_paths=validate_config_paths)

    if database is None:
        logger.critical("Database name is a required parameter.")
        raise RuntimeError("No database name was provided to get_conn().")

    port = cfg.neurobooth_config["database"]["port"]
    tunnel = SSHTunnelForwarder(
        cfg.neurobooth_config["database"]["remote_address"],
        ssh_username=cfg.neurobooth_config["database"]["remote_username"],
        ssh_config_file="~/.ssh/config",
        ssh_pkey="~/.ssh/id_rsa",
        remote_bind_address=(cfg.neurobooth_config["database"]["host"], port),
        # TODO address in config
        local_bind_address=("localhost", 6543),
    )
    tunnel.start()
    host = tunnel.local_bind_host
    port = tunnel.local_bind_port

    conn = psycopg2.connect(
        database=database,
        user=cfg.neurobooth_config["database"]["user"],
        password=cfg.neurobooth_config["database"]["pass"],
        host=host,
        port=port,
    )
    return conn


def get_study_ids(conn):
    table_study = Table("nb_study", conn=conn)
    studies_df = table_study.query()
    study_ids = studies_df.index.values.tolist()
    return study_ids


def get_subject_ids(conn, first_name, last_name):
    table_subject = Table("subject", conn=conn)
    subject_df = table_subject.query(
        where=f"LOWER(first_name_birth)=LOWER('{first_name}') AND LOWER(last_name_birth)=LOWER('{last_name}')"
    )
    return subject_df


def get_collection_ids(study_id, conn):
    table_study = Table("nb_study", conn=conn)
    studies_df = table_study.query()
    collection_ids = studies_df.loc[study_id, "collection_ids"]
    return collection_ids


def get_task_ids_for_collection(collection_id, conn):
    """

    Parameters
    ----------
    collection_id: str
        Unique identifier for collection: (The primary key of nb_collection table)
    conn : object
        Database connection

    Returns
    -------
        List[str] of task_ids for all tasks in the collection
    """
    table_collection = Table("nb_collection", conn=conn)
    collection_df = table_collection.query(where=f"collection_id = '{collection_id}'")
    (tasks_ids,) = collection_df["task_array"]
    return tasks_ids


def _new_tech_log_dict():
    """Create a new log_task dict.
    TODO(larry): Consider removing.
        Note the name should be ...task_log... not tech_log
    """
    log_task = OrderedDict()
    log_task["subject_id"] = ""
    log_task["task_id"] = ""
    log_task["log_session_id"] = ""
    log_task["task_notes_file"] = ""
    log_task["task_output_files"] = []
    log_task["date_times"] = "{" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "}"
    log_task["event_array"] = []  # marker_name:timestamp
    return log_task


def _new_session_log_dict(application_id="neurobooth_os"):
    """Create a new session_log dict."""
    session_log = OrderedDict()
    session_log["subject_id"] = ""
    session_log["study_id"] = ""
    session_log["staff_id"] = ""
    session_log["collection_id"] = ""
    session_log["application_id"] = application_id
    session_log["date"] = datetime.now().strftime("%Y-%m-%d")
    return session_log


def make_new_task_row(conn, subject_id):
    table = Table("log_task", conn=conn)
    return table.insert_rows([(subject_id,)], cols=["subject_id"])


def _make_new_appl_log_row(conn, log_entry):
    """Create a new row in the log_application table"""
    table = Table("log_application", conn=conn)
    return table.insert_rows([log_entry.values], cols=[log_entry.keys])


def _make_session_id(conn, session_log):
    """Gets or creates session id"""

    table = Table("log_session", conn=conn)
    task_df = table.query(
        where=f"subject_id = '{session_log['subject_id']}' AND date = '{session_log['date']}'"
              + f" AND collection_id = '{session_log['collection_id']}'"
    )

    # Check if session already exists
    if len(task_df):
        assert len(task_df) < 2, "More than one 'session_id' found"
        return task_df.index[0]
    # Create new session log otherwise
    vals = list(session_log.values())
    session_id = table.insert_rows([tuple(vals)], cols=list(session_log))
    return session_id


def fill_task_row(log_task_id: str, task_log_entry: TaskLogEntry, conn) -> None:
    """
    Updates a row in log_task.

    TODO: If the row isn't found, this fails silently. Needs revision in table.update_row

    Parameters
    ----------
    log_task_id
    task_log_entry
    conn

    Returns
    -------
        None
    """
    table = Table("log_task", conn=conn)
    dict_vals = task_log_entry.model_dump()

    # delete subj_date as not present in DB
    del dict_vals["subject_id_date"]
    # convert list of strings to postgres array literal format
    dict_vals['task_output_files'] = convert_to_array_literal(dict_vals['task_output_files'])
    vals = list(dict_vals.values())
    table.update_row(log_task_id, tuple(vals), cols=list(dict_vals))


def get_task_param(task_id, conn):
    """

    Parameters
    ----------
    task_id : str
        The unique identifier for a task
    conn : object
        database connection

    Returns
    -------
        tuple of task parameters
    """
    # task_data, stimulus, instruction
    table_task = Table("nb_task", conn=conn)
    task_df = table_task.query(where=f"task_id = '{task_id}'")
    (device_ids,) = task_df["device_id_array"]
    (sensor_ids,) = task_df["sensor_id_array"]
    (stimulus_id,) = task_df["stimulus_id"]
    (instr_id,) = task_df["instruction_id"]

    instr_kwargs: Optional[InstructionArgs] = None

    if instr_id is not None:
        instr_kwargs = _get_instruction_kwargs_from_file(instr_id)
    return (
        stimulus_id,
        device_ids,
        sensor_ids,
        instr_kwargs,
    )  # XXX: name similarly in calling function


def _get_instruction_kwargs_from_file(instruction_id: str) -> InstructionArgs:
    """Return InstructionArgs with the given id from yaml parameter file."""
    file_name = instruction_id + ".yml"
    instr_param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file_name, 'instructions')
    param_parser: str = instr_param_dict['arg_parser']
    parser_func = str_fileid_to_eval(param_parser)
    args: InstructionArgs = parser_func(**instr_param_dict)
    assert isinstance(args, InstructionArgs)
    return args


def log_task_params(conn, stimulus_id: str, log_task_id: str, task_param_dictionary: Dict[str, Any]):
    """
    Logs task parameters (specifically, the stimulus params and instruction params) to the database.
    @param conn: postgres database connection
    @param stimulus_id: primary key from the nb_stimulus table. Identifies the current stimulus
    @param log_task_id: primary key from the log_task table for the current task and session
    @param task_param_dictionary: dictionary of string keys and values containing the data to be logged
    @return: None
    """
    for key, value in task_param_dictionary.items():
        value_type = str(type(value))
        args = {
            "log_task_id": log_task_id,
            "stimulus_id": stimulus_id,
            "key": key,
            "value": value,
            "value_type": value_type,
        }
        _log_task_parameter(conn, args)
    conn.commit()


def _log_task_parameter(conn, value_dict: Dict[str, Any]):
    query = "INSERT INTO log_task_param " \
            "(log_task_id, stimulus_id, key, value, value_type)  " \
            " VALUES " \
            " (%(log_task_id)s, %(stimulus_id)s, %(key)s, %(value)s, %(value_type)s)"

    cursor = conn.cursor()
    cursor.execute(query, value_dict)


def get_stimulus_kwargs_from_file(stimulus_id):
    """Get task (stimulus) parameters from a yaml file."""

    stimulus_file_name = stimulus_id + ".yml"
    task_param_dict = stim_param_reader.get_param_dictionary(stimulus_file_name, 'stimuli')
    stim_file = task_param_dict["stimulus_file"]
    return stim_file, task_param_dict


def _get_sensor_kwargs(sens_id, conn):
    table_sens = Table("nb_sensor", conn=conn)
    task_df = table_sens.query(where=f"sensor_id = '{sens_id}'")
    param = task_df.iloc[0].to_dict()
    return param


def _get_dev_sn(dev_id, conn):
    table_sens = Table("nb_device", conn=conn)
    device_df = table_sens.query(where=f"device_id = '{dev_id}'")
    sn = device_df["device_sn"]
    if len(sn) == 0:
        return None
    return sn[0]


def map_database_to_deviceclass(dev_id, dev_id_param):
    # Convert SN and sens param from metadata to kwarg for device function
    # input: dict, from _get_device_kwargs
    #   dict with keys: "SN":"xx", "sensors": {"sensor_ith":{parameters}}

    info = dev_id_param
    kwarg = {}
    kwarg["device_id"] = dev_id
    kwarg["sensor_ids"] = list(info["sensors"])

    if "mock_Mbient" in dev_id:
        kwarg["name"] = dev_id
        k = list(info["sensors"])[0]
        kwarg["srate"] = int(info["sensors"][k]["temporal_res"])

    elif "mock_Intel" in dev_id:
        kwarg["name"] = dev_id
        k = list(info["sensors"])[0]
        kwarg["srate"] = int(info["sensors"][k]["temporal_res"])
        kwarg["sizex"] = int(info["sensors"][k]["spatial_res_x"])
        kwarg["sizey"] = int(info["sensors"][k]["spatial_res_y"])

    elif "Intel" in dev_id:
        kwarg["camindex"] = [int(dev_id[-1]), info["SN"]]

        for k in info["sensors"].keys():
            if "rgb" in k:
                size_x = int(info["sensors"][k]["spatial_res_x"])
                size_y = int(info["sensors"][k]["spatial_res_y"])
                kwarg["size_rgb"] = (size_x, size_y)
                kwarg["fps_rgb"] = int(info["sensors"][k]["temporal_res"])

            elif "depth" in k:
                size_x = int(info["sensors"][k]["spatial_res_x"])
                size_y = int(info["sensors"][k]["spatial_res_y"])
                kwarg["size_depth"] = (size_x, size_y)
                kwarg["fps_depth"] = int(info["sensors"][k]["temporal_res"])

    elif "Mbient" in dev_id:
        kwarg["dev_name"] = dev_id.split("_")[1]
        kwarg["mac"] = info["SN"]
        for k in info["sensors"].keys():
            if "acc" in k:
                kwarg["acc_hz"] = int(info["sensors"][k]["temporal_res"])
            elif "gyro" in k:
                kwarg["gyro_hz"] = int(info["sensors"][k]["temporal_res"])

    elif "FLIR_blackfly" in dev_id:
        kwarg["camSN"] = info["SN"]
        (k,) = info["sensors"].keys()
        # TODO test asserting assert(len(list(info['sensors']))==1) raise
        # f"{dev_id} should have only one sensor"
        kwarg["fps"] = int(info["sensors"][k]["temporal_res"])
        kwarg["sizex"] = int(info["sensors"][k]["spatial_res_x"])
        kwarg["sizey"] = int(info["sensors"][k]["spatial_res_y"])

    elif "Mic_Yeti" in dev_id:
        # TODO test asserting assert(len(list(info['sensors']))==1) raise
        # f"{dev_id} should have only one sensor"
        (k,) = info["sensors"].keys()
        kwarg["RATE"] = int(info["sensors"][k]["temporal_res"])
        kwarg["CHUNK"] = int(info["sensors"][k]["spatial_res_x"])

    elif "Eyelink" in dev_id:
        kwarg["ip"] = info["SN"]
        # TODO test asserting assert(len(list(info['sensors']))==1) raise
        # f"{dev_id} should have only one sensor"
        (k,) = info["sensors"].keys()
        kwarg["sample_rate"] = int(info["sensors"][k]["temporal_res"])
    elif "Mouse" in dev_id:
        return kwarg
    elif "IPhone" in dev_id:
        (k,) = info["sensors"].keys()
    else:
        print(
            f"Device id parameters not found for {dev_id} in map_database_to_deviceclass"
        )

    return kwarg


def _get_device_kwargs(task_id, conn):
    stim_id, dev_ids, sens_ids, _ = get_task_param(task_id, conn)
    dev_kwarg = {}
    for dev_id, dev_sens_ids in zip(dev_ids, sens_ids):
        # TODO test that dev_sens_ids are from correct dev_id, eg. dev_sens_ids =
        # {Intel_D455_rgb_1,Intel_D455_depth_1} dev_id= Intel_D455_x
        dev_id_param = {}
        dev_id_param["SN"] = _get_dev_sn(dev_id, conn)

        dev_id_param["sensors"] = {}
        for sens_id in dev_sens_ids:
            if len(sens_id):
                dev_id_param["sensors"][sens_id] = _get_sensor_kwargs(sens_id, conn)

        kwarg = map_database_to_deviceclass(dev_id, dev_id_param)

        dev_kwarg[dev_id] = kwarg
    return dev_kwarg


def get_device_kwargs_by_task(collection_id, conn) -> OrderedDict:
    # Get devices kwargs for all the tasks
    # outputs dict with keys = stimulus_id, vals = dict with dev parameters

    tasks = get_task_ids_for_collection(collection_id, conn)

    tasks_kwarg = OrderedDict()
    for task in tasks:
        stim_id, *_ = get_task_param(task, conn)
        task_kwarg = _get_device_kwargs(task, conn)
        tasks_kwarg[stim_id] = task_kwarg

    return tasks_kwarg


def read_sensors() -> Dict[str, SensorArgs]:
    """Return dictionary of sensor_id to SensorArgs for all yaml sensor parameter files."""

    directory: str = get_cfg_path("sensors")
    sens_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, 'sensors')
        param_parser: str = param_dict['arg_parser']
        parser_func = str_fileid_to_eval(param_parser)
        args: SensorArgs = parser_func(**param_dict)
        sens_dict[file_name] = args
    return sens_dict


def read_devices() -> Dict[str, DeviceArgs]:
    """Return dictionary of device_id to DeviceArgs for all yaml device parameter files."""

    directory: str = get_cfg_path("devices")
    sens_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, 'devices')
        param_parser: str = param_dict['arg_parser']
        parser_func = str_fileid_to_eval(param_parser)
        args: DeviceArgs = parser_func(**param_dict)
        sens_dict[file_name] = args
    return sens_dict


def read_instructions() -> Dict[str, InstructionArgs]:
    """Return dictionary of instruction_id to InstructionArgs for all yaml instruction parameter files."""

    directory: str = get_cfg_path("instructions")
    sens_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, 'instructions')
        param_parser: str = param_dict['arg_parser']
        parser_func = str_fileid_to_eval(param_parser)
        args: InstructionArgs = parser_func(**param_dict)
        sens_dict[file_name] = args
    return sens_dict


def read_stimuli() -> Dict[str, StimulusArgs]:
    """Return dictionary of stimulus_id to StimulusArgs for all yaml stimulus parameter files."""

    directory: str = get_cfg_path("stimuli")
    stim_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, 'stimuli')
        param_parser: str = param_dict['arg_parser']
        parser_func = str_fileid_to_eval(param_parser)
        args: StimulusArgs = parser_func(**param_dict)
        stim_dict[file_name] = args
    return stim_dict


def read_tasks() -> Dict[str, RawTaskParams]:
    """Return dictionary of task_id to TaskArgs for all yaml task parameter files."""

    directory: str = get_cfg_path("tasks")
    task_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, 'tasks')
        param_parser: str = param_dict['arg_parser']
        parser_func = str_fileid_to_eval(param_parser)
        args: RawTaskParams = parser_func(**param_dict)
        task_dict[file_name] = args
    return task_dict


def _read_all_task_params():
    """Returns a dictionary containing all task parameters of all types"""
    params = {}
    params["tasks"] = read_tasks()
    params["stimuli"] = read_stimuli()
    params["instructions"] = read_instructions()
    params["devices"] = read_devices()
    params["sensors"] = read_sensors()
    return params


def build_tasks_for_collection(collection_id: str, conn) -> Dict[str, TaskArgs]:
    task_ids = get_task_ids_for_collection(collection_id, conn)
    task_dict: Dict[str:TaskArgs] = {}
    param_dictionary = _read_all_task_params()
    for task_id in task_ids:
        raw_task_args: RawTaskParams = param_dictionary["tasks"][task_id]
        stim_args: StimulusArgs = param_dictionary["stimuli"][raw_task_args.stimulus_id]
        task_constructor = stim_args.stimulus_file
        instr_args: Optional[InstructionArgs] = None
        if raw_task_args.instruction_id:
            instr_args = param_dictionary["instructions"][raw_task_args.instruction_id]
        device_ids = raw_task_args.device_id_array
        device_args = []
        for dev_id in device_ids:
            dev_args: DeviceArgs = param_dictionary["devices"][dev_id]
            sensor_args = []
            for sens_id in dev_args.sensor_ids:
                sensor_args.append(param_dictionary["sensors"][sens_id])
            dev_args.sensor_array = sensor_args
            device_args.append(dev_args)

        task_constructor_callable = str_fileid_to_eval(task_constructor)
        task_args: TaskArgs = TaskArgs(
            task_id=task_id,
            task_constructor_callable=task_constructor_callable,
            stim_args=stim_args,
            instr_args=instr_args,
            device_args=device_args
        )
        task_dict[task_id] = task_args
    return task_dict

