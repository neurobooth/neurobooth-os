# -*- coding: utf-8 -*-
import importlib
import logging
import os
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, Optional, List

from pydantic import BaseModel
from sshtunnel import SSHTunnelForwarder
import psycopg2
from psycopg2.extensions import connection
from neurobooth_terra import Table

import neurobooth_os.config as cfg
from neurobooth_os.iout import stim_param_reader
from neurobooth_os.iout.stim_param_reader import InstructionArgs, SensorArgs, get_cfg_path, DeviceArgs, StimulusArgs, \
    RawTaskParams, TaskArgs, StudyArgs, CollectionArgs
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


def get_database_connection(database: Optional[str] = None, validate_config_paths: bool = True) -> connection:
    """Gets connector to the database

    :param database: If provided, override the database name in the configration.
    :param validate_config_paths: True if the config file path should be validated.
        This should generally be True outside test scenarios
    :returns: Connector to psycopg database
    """
    import neurobooth_os.log_manager as log_man
    log_man.make_default_logger(log_level=logging.ERROR, validate_paths=validate_config_paths)

    database_info = cfg.neurobooth_config.database
    tunnel = SSHTunnelForwarder(
        database_info.remote_host,
        ssh_username=database_info.remote_user,
        ssh_config_file="~/.ssh/config",
        ssh_pkey="~/.ssh/id_rsa",
        remote_bind_address=(database_info.host, database_info.port),
        local_bind_address=("localhost", 6543),  # TODO: address in config
    )
    tunnel.start()
    host = tunnel.local_bind_host
    port = tunnel.local_bind_port

    conn = psycopg2.connect(
        database=database_info.dbname if database is None else database,
        user=database_info.user,
        password=database_info.password,
        host=host,
        port=port,
    )
    return conn


def get_study_ids() -> List[str]:
    return list(read_studies().keys())


def get_subject_ids(conn: connection, first_name, last_name):
    table_subject = Table("subject", conn=conn)
    subject_df = table_subject.query(
        where=f"LOWER(first_name_birth)=LOWER('{first_name}') AND LOWER(last_name_birth)=LOWER('{last_name}')"
    )
    return subject_df


def get_collection_ids(study_id) -> List[str]:
    studies = read_studies()
    study: StudyArgs = studies[study_id]
    return study.collection_ids


def get_task_ids_for_collection(collection_id) -> List[str]:
    """

    Parameters
    ----------
    collection_id: str
        Unique identifier for collection as embedded in the yaml file name for collection

    Returns
    -------
        List[str] of task_ids for all tasks in the collection
    """
    collections = read_collections()
    collection: CollectionArgs = collections[collection_id]
    return collection.task_ids


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


def make_new_task_row(conn: connection, subject_id):
    table = Table("log_task", conn=conn)
    return table.insert_rows([(subject_id,)], cols=["subject_id"])


def _make_new_appl_log_row(conn: connection, log_entry):
    """Create a new row in the log_application table"""
    table = Table("log_application", conn=conn)
    return table.insert_rows([log_entry.values], cols=[log_entry.keys])


def _make_session_id(conn: connection, session_log):
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


def fill_task_row(log_task_id: str, task_log_entry: TaskLogEntry, conn: connection) -> None:
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


def get_stimulus_id(task_id: str) -> str:
    task : RawTaskParams = read_tasks()[task_id]
    return task.stimulus_id


def get_device_ids(task_id: str) -> List[str]:
    task : RawTaskParams = read_tasks()[task_id]
    return task.device_id_array


def _get_instruction_kwargs(instruction_id: str) -> Optional[InstructionArgs]:
    """Get InstructionArgs from instruction yml files."""
    if instruction_id is not None:
        file_name = instruction_id + ".yml"
        instr_param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file_name, 'instructions')
        param_parser: str = instr_param_dict['arg_parser']
        parser_func = str_fileid_to_eval(param_parser)
        args: InstructionArgs = parser_func(**instr_param_dict)
        return args
    else:
        return None


def log_task_params(conn: connection, stimulus_id: str, log_task_id: str, task_param_dictionary: Dict[str, Any]):
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


def _log_task_parameter(conn: connection, value_dict: Dict[str, Any]):
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


def _get_sensor_kwargs(sens_id, conn: connection):
    table_sens = Table("nb_sensor", conn=conn)
    task_df = table_sens.query(where=f"sensor_id = '{sens_id}'")
    param = task_df.iloc[0].to_dict()
    return param


def _get_dev_sn(dev_id:str) -> Optional[str]:
    """
    Parameters
    ----------
    dev_id : str
        the id of the device, which is also the file-name for the yml file that contains the dev params
         (excluding the ".yml" file extension)

    Returns
    -------
        the serial number of the device, or None
    """
    devices = read_devices()
    device : DeviceArgs = devices[dev_id]
    sn = device.device_sn
    if len(sn) == 0:
        return None
    return sn


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


def _get_device_kwargs(task_id, conn: connection):
    task: RawTaskParams = get_task(task_id)
    dev_kwarg = {}
    for dev_id, dev_sens_ids in zip(task.device_id_array, task.sensor_id_array):
        # TODO test that dev_sens_ids are from correct dev_id, eg. dev_sens_ids =
        # {Intel_D455_rgb_1,Intel_D455_depth_1} dev_id= Intel_D455_x
        dev_id_param = {}
        dev_id_param["SN"] = _get_dev_sn(dev_id)

        dev_id_param["sensors"] = {}
        for sens_id in dev_sens_ids:
            if len(sens_id):
                dev_id_param["sensors"][sens_id] = _get_sensor_kwargs(sens_id, conn)
        kwarg = map_database_to_deviceclass(dev_id, dev_id_param)
        dev_kwarg[dev_id] = kwarg
    return dev_kwarg


def get_device_kwargs_by_task(collection_id, conn: connection) -> OrderedDict:
    """
    Gets devices kwargs for all the tasks in the collection

    Parameters
    ----------
    collection_id str
        Unique identifier for collection
    conn Object
        database connection

    Returns
    -------
        Dict with keys = stimulus_id, vals = dict with dev parameters
    """

    task_ids = get_task_ids_for_collection(collection_id)

    tasks_kwarg = OrderedDict()
    for task_id in task_ids:
        stim_id = get_stimulus_id(task_id)
        task_kwarg = _get_device_kwargs(task_id, conn)
        tasks_kwarg[stim_id] = task_kwarg
    return tasks_kwarg


def read_sensors() -> Dict[str, SensorArgs]:
    """Return dictionary of sensor_id to SensorArgs for all yaml sensor parameter files."""
    folder = 'sensors'
    return _parse_files(folder)


def _dynamic_parse(file: str, param_type: str) -> BaseModel:
    param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, param_type)
    param_parser: str = param_dict['arg_parser']
    parser_func = str_fileid_to_eval(param_parser)
    return parser_func(**param_dict)


def _parse_files(folder):
    directory: str = get_cfg_path(folder)
    result_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        result_dict[file_name] = _dynamic_parse(file, folder)
    return result_dict

def read_devices() -> Dict[str, DeviceArgs]:
    """Return dictionary of device_id to DeviceArgs for all yaml device parameter files."""
    folder = 'devices'
    return _parse_files(folder)


def read_instructions() -> Dict[str, InstructionArgs]:
    """Return dictionary of instruction_id to InstructionArgs for all yaml instruction parameter files."""

    folder = 'instructions'
    return _parse_files(folder)


def read_stimuli() -> Dict[str, StimulusArgs]:
    """Return dictionary of stimulus_id to StimulusArgs for all yaml stimulus parameter files."""
    folder = 'stimuli'
    return _parse_files(folder)


def read_tasks() -> Dict[str, RawTaskParams]:
    """Return dictionary of task_id to RawTaskParams for all yaml task parameter files."""

    folder = 'tasks'
    return _parse_files(folder)


def read_studies() -> Dict[str, StudyArgs]:
    """Return dictionary of study_id to StudyArgs for all yaml study parameter files."""

    folder = 'studies'
    return _parse_files(folder)


def read_collections() -> Dict[str, CollectionArgs]:
    """Return dictionary of collection_id to CollectionArgs for all yaml collection parameter files."""

    folder = 'collections'
    directory: str = get_cfg_path(folder)
    return _parse_files(folder)


def get_task(task_id:str) -> RawTaskParams:
    tasks = read_tasks()
    return tasks[task_id]

def read_all_task_params():
    """Returns a dictionary containing all task parameters of all types"""
    params = {}
    params["tasks"] = read_tasks()
    params["stimuli"] = read_stimuli()
    params["instructions"] = read_instructions()
    params["devices"] = read_devices()
    params["sensors"] = read_sensors()
    return params


def build_tasks_for_collection(collection_id: str) -> Dict[str, TaskArgs]:
    """
    Constructs a dictionary of task_ids to TaskArgs for every task in the collection
    Parameters
    ----------
    collection_id str
        The unique identifier for the collection
    conn object
        A database connection

    Returns
    -------
        Dictionary with task_id = TaskArgs
    """
    task_ids = get_task_ids_for_collection(collection_id)
    task_dict: Dict[str:TaskArgs] = {}
    param_dictionary = read_all_task_params()
    for task_id in task_ids:
        task_args = build_task(param_dictionary, task_id)
        task_dict[task_id] = task_args
    return task_dict


def build_task(param_dictionary, task_id) -> TaskArgs:
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
    return task_args

