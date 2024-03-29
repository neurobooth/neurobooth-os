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


def _get_sensor(sens_id) -> SensorArgs:
    """
    Returns SensorArgs for sensor with the given id
    """
    return read_sensors()[sens_id]


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


def build_task(param_dictionary, task_id:str) -> TaskArgs:
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

