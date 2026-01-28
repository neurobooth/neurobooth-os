# -*- coding: utf-8 -*-
import importlib
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime
from typing import Dict, Any, Optional, List
from neurobooth_os.util.nb_types import Subject

import pandas as pd
from pandas import DataFrame
from pydantic import BaseModel
from sshtunnel import SSHTunnelForwarder
import psycopg2
from psycopg2.extensions import connection
from neurobooth_terra import Table

import neurobooth_os.config as cfg
from neurobooth_os.iout import stim_param_reader
from neurobooth_os.iout.stim_param_reader import InstructionArgs, SensorArgs, get_cfg_path, DeviceArgs, StimulusArgs, \
    RawTaskParams, TaskArgs, StudyArgs, CollectionArgs
from neurobooth_os.msg.messages import Message, MsgBody
from neurobooth_os.util.task_log_entry import TaskLogEntry, convert_to_array_literal


class LogSession(BaseModel):
    log_session_id: Optional[int] = None
    subject_id: Optional[str] = None
    study_id: Optional[str] = None
    staff_id: Optional[str] = None
    collection_id: Optional[str] = None
    application_id: str = "neurobooth_os"
    application_version: Optional[str]
    config_version: Optional[str]
    date: datetime = datetime.now()


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


def get_database_connection(database: Optional[str] = None) -> connection:
    database_info = cfg.neurobooth_config.database
    if database_info.ssh_tunnel and database_info.host not in ["127.0.0.1", "localhost"]:
        # If the DB is not on this host, use SSH tunneling for access
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
    else:
        host = database_info.host
        port = database_info.port

    db = database_info.dbname if database is None else database

    conn = psycopg2.connect(
        database=db,
        user=database_info.user,
        password=database_info.password,
        host=host,
        port=port,
    )
    return conn


def clear_msg_queue(conn):
    """
    Clears message_queue table. Intended for use at the start of a session so errors in prior session don't leave
    unhandled messages.
    TODO: Copy messages to log before clearing
    Parameters
    ----------
    conn: connection    A database connection

    Returns
    -------
    None
    """
    table = Table("message_queue", conn=conn)
    table.delete_row()


def post_message(msg: Message, conn: connection = None) -> str:
    """
    Posts a new message to the database that mediates between message senders and receivers

    Parameters
    ----------
    msg: Message        The Message to be posted
    conn: connection    A database connection

    Returns
    -------
    pk_val : str | None
            The primary keys of the row inserted into.
            If multiple rows are inserted, returns None.

    """
    if conn is None:
        with get_database_connection() as conn:
            post_message(msg, conn)

    else:
        table = Table("message_queue", conn=conn)
        body = msg.body.model_dump_json()
        return table.insert_rows([(str(msg.uuid),
                                   msg.msg_type,
                                   msg.full_msg_type(),
                                   msg.source,
                                   msg.destination,
                                   msg.priority,
                                   body)],
                                 cols=["uuid", "msg_type", "full_msg_type", "source", "destination", 'priority', 'body'])


def read_next_message(destination: str, conn: connection, msg_type: str = None) -> Optional[Message]:
    f"""
    Returns a Message representing the next message to be handled by 
    the calling process. Code representing the message {destination} would call this message to check for new messages.
    If msg_type is None, LslRecording messages and some others are skipped as they have their own message handling loop.
    
    NOTE: A MESSAGE CAN ONLY BE READ ONCE using this method as the message's time_read value is updated before 
    returning the query results. Only rows where time_read is NULL are returned here. 
    
    Parameters
    ----------
    destination: str    The identifier for the process that is the intended receiver of the message
    conn: connection    A database connection
    msg_type: str       The type of message (a string representation of the message's body class, 
                        e.g. 'FramePreviewRequest') or another string indicating the type of messages to read. 
                        Defaults to None


    Returns a Message or None. Clients should check for None before trying to use the results. 
    -------

    """
    if msg_type is None:
        msg_type_stmt = \
            " and msg_type NOT IN ('LslRecording', 'RecordingStarted', 'RecordingStopped', 'MbientResetResults') "
    elif msg_type == 'paused_msg_types':
        msg_type_stmt = (" and msg_type IN ('ResumeSessionRequest', 'CancelSessionRequest', 'CalibrationRequest', "
                         "'TerminateServerRequest', 'MbientResetResults') ")
    else:
        msg_type_stmt = f" and msg_type = '{msg_type}' "

    time_read = datetime.now()
    update_str = \
        f''' 
        with selection as
            (
            select *  
            from message_queue
            where time_read is NULL
            and destination = '{destination}'
            {msg_type_stmt}
            order by priority desc, id asc
            limit 1
            )
        UPDATE message_queue
        SET time_read = now() 
        from selection
        where message_queue.id = selection.id
        returning message_queue.id, message_queue.uuid, message_queue.msg_type, message_queue.full_msg_type, 
        message_queue.priority, message_queue.source, message_queue.destination, message_queue.time_created, 
        message_queue.time_read, message_queue.body     
     '''

    curs = conn.cursor()
    curs.execute(update_str)
    msg_df: DataFrame = pd.DataFrame(curs.fetchall())
    conn.commit()
    curs.close()
    if msg_df.empty:
        return None
    field_names = [i[0] for i in curs.description]
    msg_df = msg_df.set_axis(field_names, axis='columns')
    body = msg_df['body'].iloc[0]
    uuid = msg_df['uuid'].iloc[0]
    msg_type = msg_df['msg_type'].iloc[0]
    msg_type_full = msg_df['full_msg_type'].iloc[0]
    priority = msg_df['priority'].iloc[0]
    source = msg_df['source'].iloc[0]
    destination = msg_df['destination'].iloc[0]
    body_constructor = str_fileid_to_eval(msg_type_full)
    msg_body: MsgBody = body_constructor(**body)
    msg = Message(body=msg_body, uuid=uuid, msg_type=msg_type, source=source, destination=destination,
                  priority=priority)
    return msg


def get_study_ids() -> List[str]:
    return list(read_studies().keys())


def get_subject_ids(conn: connection, first_name, last_name):
    table_subject = Table("subject", conn=conn)
    f_name = _escape_name_string(first_name)
    l_name = _escape_name_string(last_name)

    subject_df = table_subject.query(
        where=f"LOWER(first_name_birth)=LOWER('{f_name}') AND LOWER(last_name_birth)=LOWER('{l_name}')"
    )
    return subject_df


def get_subject_by_id(conn: connection, subject_id: str) -> Optional[Subject]:
    """
    Returns the Subject associated with the give subject_id, or None if no match is found.

    We also attempt to get auxiliary data from rc_contact, but this data table may be missing or corrupt,
    so we make sure it exists first and attempt to tolerate any error coming from Postgres.
    """
    subject_id = subject_id.strip()
    # We do two separate queries in case the rc_contact table doesn't have any matching records due to,
    # for example, an issue with the REDCap update timing.  We always want a result if there's a matching
    # record in the subject table.  Hitting both tables with a single join query would cause zero records to be returned
    table_subject = Table("subject", conn=conn)
    subject_df = table_subject.query(where=f"LOWER(subject_id)=LOWER('{subject_id}')")

    contact_query = f"""select first_name_contact, last_name_contact 
        from rc_contact 
        where LOWER(subject_id) = Lower('{subject_id}')
        order by start_time_contact desc
        limit 1
    """

    if subject_df.empty:
        return None
    else:
        # populate the Subject model with the data we found
        subj = Subject(
            subject_id=subject_id,
            first_name_birth=subject_df['first_name_birth'].iloc[0],
            middle_name_birth=subject_df['middle_name_birth'].iloc[0],
            last_name_birth=subject_df['last_name_birth'].iloc[0],
            date_of_birth=subject_df['date_of_birth_subject'].iloc[0],
            preferred_first_name="",
            preferred_last_name="",
        )
        # Get additional data from rc_contact, if it's available and the table is healthy
        # verify that the contact table (rc_contact) exists, if not just return what we got from the subject table
        curs = conn.cursor()
        curs.execute("select * from information_schema.tables where table_name=%s", ('rc_contact',))
        # if rc_contact *does* exist, try to query it for the additional info. Swallow any exceptions that occur
        if bool(curs.rowcount):
            try:
                # Get the column names from the cursor description
                curs.execute(contact_query)
                results = curs.fetchall()
                column_names = [desc[0] for desc in curs.description]

                # Create the DataFrame
                contact_df = pd.DataFrame(results, columns=column_names)
                conn.commit()
                curs.close()

                if not contact_df.empty:
                    subj.preferred_first_name = str(contact_df['first_name_contact'].iloc[0])
                    subj.preferred_last_name = str(contact_df['last_name_contact'].iloc[0])
            except psycopg2.Error as db_error:  # Catch any psycopg2 database exception
                import neurobooth_os.log_manager as log_man
                log_man.APP_LOGGER.error(f"A database exception occurred. Exception was: {repr(db_error)}",
                                         exc_info=sys.exc_info())
            finally:
                if curs is not None:
                    curs.close()
        return subj


def _escape_name_string(name: str) -> str:
    """ Escapes a single quote in the name (as in, e.g. "O'neil"), if one exists."""
    name = name.strip()
    if "'" in name:
        return f'''{name.replace("'", "''")}'''
    else:
        return name


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


def get_session_start_end_slides_for_collection(collection_id) -> (str, str):
    collections = read_collections()
    collection: CollectionArgs = collections[collection_id]
    return collection.session_start_slide, collection.session_end_slide


def new_task_log_dict():
    """Create a new log_task dict.
    TODO(larry): Consider removing.
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


def make_new_task_row(conn: connection, subject_id):
    table = Table("log_task", conn=conn)
    return table.insert_rows([(subject_id,)], cols=["subject_id"])


def _make_new_appl_log_row(conn: connection, log_entry):
    """Create a new row in the log_application table"""
    table = Table("log_application", conn=conn)
    return table.insert_rows([log_entry.values], cols=[log_entry.keys])


def make_session_id(conn: connection, log_session: LogSession) -> int:
    """Gets or creates session id"""

    table = Table("log_session", conn=conn)
    datetime_str = log_session.date.strftime("%Y-%m-%d")
    task_df = table.query(
        where=f"subject_id = '{log_session.subject_id}' AND date = '{datetime_str}'"
              + f" AND collection_id = '{log_session.collection_id}'"
    )

    # Check if session already exists
    if len(task_df):
        assert len(task_df) < 2, "More than one 'session_id' found"
        return task_df.index[0]
    # Create new session log otherwise
    log_sess: Dict = log_session.model_dump()
    del log_sess["log_session_id"]
    vals = list(log_sess.values())
    session_id = table.insert_rows([tuple(vals)], cols=list(log_sess))
    return int(session_id)


def fill_task_row(task_log_entry: TaskLogEntry, conn: connection) -> None:
    """
    Updates a row in log_task.

    TODO: If the row isn't found, this fails silently. Needs revision in table.update_row

    Parameters
    ----------
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
    table.update_row(task_log_entry.log_task_id, tuple(vals), cols=list(dict_vals))


def get_stimulus_id(task_id: str) -> str:
    task: RawTaskParams = read_tasks()[task_id]
    return task.stimulus_id


def get_device_ids(task_id: str) -> List[str]:
    task: RawTaskParams = read_tasks()[task_id]
    return task.device_id_array


def _fill_device_param_row(conn: connection, device: DeviceArgs) -> Optional[str]:
    table = Table("log_device_param", conn=conn)
    dict_vals = device.model_dump()

    # remove redundant data from device before saving
    if 'ENV_devices' in dict_vals:
        del dict_vals['ENV_devices']

    # remove unwanted element from each sensor
    for sensor in dict_vals['sensor_array']:
        del sensor['ENV_devices']

    log_device = OrderedDict()
    log_device["device_id"] = dict_vals['device_id']
    log_device["sensor_array"] = json.dumps(dict_vals['sensor_array'])
    log_device["device_name"] = dict_vals['device_name']
    if 'device_sn' in dict_vals:
        log_device["device_sn"] = dict_vals['device_sn']
    log_device["wearable_bool"] = dict_vals['wearable_bool']
    log_device["arg_parser"] = dict_vals['arg_parser']

    # log the remaining data, skipping anything that already gets its own column
    # Note: The dictionary key in dict_val must match the database column name,
    # so we're stuck with names like "wearable_bool"
    handled_keys = list(log_device.keys())
    for key in handled_keys:
        if key in dict_vals:
            del dict_vals[key]
    json_string = json.dumps(dict_vals)
    log_device['additional_data'] = json_string

    t = tuple(list(log_device.values()))
    pkey = table.insert_rows([t], cols=list(log_device.keys()))
    return pkey


def log_devices(conn: connection = None, task_args_list: Optional[List[TaskArgs]] = None) -> Dict[str, str]:
    """
    Logs all the devices used in a session so that they can be shared in the db across the tasks that use them
    Parameters
    Returns a dictionary of device_id to log_device_param table primary key
    ----------
    conn
    task_args_list

    Returns
    -------
    a dictionary of device_id to the primary key for the log_device_param table
    """
    device_id_dict = {}
    device_pkey_dict = {}
    for task in task_args_list:
        for device in task.device_args:
            device_id_dict[device.device_id] = device
    if conn is None:
        conn = get_database_connection()
    for device in list(device_id_dict.values()):
        primary_key = _fill_device_param_row(conn, device)
        device_pkey_dict[device.device_id] = primary_key
    return device_pkey_dict


def log_task_params(conn: connection, log_task_id: str, device_log_entry_dict: Dict[str, int], task_args: TaskArgs):
    """
    Logs task parameters (specifically, the stimulus params and instruction params) to the database.
    @param conn: postgres database connection
    @param log_task_id: primary key from the log_task table for the current task and session
    @param task_args: Hierarchical Pydantic model of the data to be logged
    @return: None

    Parameters
    ----------
    conn: database connection
    log_task_id: the id assigned to the combination of task and session in the log_task table
    device_log_entry_dict: a dictionary of device_id to the primary key for the log_device_param table
    task_args: The TaskArgs object to log
    """

    table = Table("log_task_param", conn=conn)
    dict_vals = task_args.model_dump()
    if 'ENV_devices' in dict_vals:
        del dict_vals['ENV_devices']
    if 'task_instance' in dict_vals:
        del dict_vals['task_instance']

    log_task = OrderedDict()
    log_task["log_task_id"] = log_task_id
    log_task["task_id"] = dict_vals['task_id']

    # remap device entries to their log_device_param keys
    device_id_list = []
    for d in dict_vals["device_args"]:
        device_id_list.append(device_log_entry_dict[d['device_id']])
    log_task['log_device_ids'] = device_id_list
    del dict_vals['device_args']

    if 'instr_args' in dict_vals:
        if dict_vals['instr_args'] is not None and 'ENV_devices' in dict_vals['instr_args']:
            del dict_vals['instr_args']['ENV_devices']
            log_task["instr_args"] = json.dumps(dict_vals['instr_args'])

    if 'ENV_devices' in dict_vals['stim_args']:
        del dict_vals['stim_args']['ENV_devices']
    log_task["stim_args"] = json.dumps(dict_vals['stim_args'])
    log_task["arg_parser"] = str(dict_vals['arg_parser'])
    log_task["task_constructor_callable"] = str(dict_vals['task_constructor_callable'])

    # log the remaining data, skipping anything that already gets its own column
    # Note: The dictionary key in dict_val must match the database column name.
    handled_keys = list(log_task.keys())
    for key in list(dict_vals.keys()):
        if key in handled_keys:
            del dict_vals[key]
    json_string = json.dumps(dict_vals)
    log_task['additional_data'] = json_string

    t = tuple(list(log_task.values()))
    table.insert_rows([t], cols=list(log_task.keys()))


def _get_sensor(sens_id) -> SensorArgs:
    """
    Returns SensorArgs for sensor with the given id
    """
    return read_sensors()[sens_id]


def read_sensors() -> Dict[str, SensorArgs]:
    """Return dictionary of sensor_id to SensorArgs for all yaml sensor parameter files."""
    folder = 'sensors'
    return _parse_files(folder)


def _dynamic_parse(file: str, param_type: str, env_dict: Dict[str, Any]) -> BaseModel:
    param_dict: Dict[str:Any] = stim_param_reader.get_param_dictionary(file, param_type)
    param_dict.update(env_dict)
    param_parser: str = param_dict['arg_parser']
    parser_func = str_fileid_to_eval(param_parser)
    return parser_func(**param_dict)


def _parse_files(folder):
    env_dict = stim_param_reader.get_param_dictionary("environment.yml", "")
    directory: str = get_cfg_path(folder)
    result_dict = {}
    for file in os.listdir(directory):
        file_name = os.fsdecode(file).split(".")[0]
        result_dict[file_name] = _dynamic_parse(file, folder, env_dict)
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


def get_task(task_id: str) -> RawTaskParams:
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


def build_tasks_for_collection(collection_id: str, selected_tasks: Optional[List[str]] = None) -> Dict[str, TaskArgs]:
    """
    Constructs a dictionary of task_ids to TaskArgs for every task in the collection
    Parameters
    ----------
    collection_id str
        The unique identifier for the collection
    selected_tasks Optional[List[str]]
        An optional list of task IDs used to filter the tasks in the collection.
        If present, Only those tasks in selected tasks should be returned.

    Returns
    -------
        Dictionary with task_id = TaskArgs
    """
    if selected_tasks is None:
        task_ids: List[str] = get_task_ids_for_collection(collection_id)
    else:
        task_ids: List[str] = selected_tasks
    task_dict: Dict[str:TaskArgs] = {}
    param_dictionary = read_all_task_params()
    for task_id in task_ids:
        task_args = build_task(param_dictionary, task_id)
        task_dict[task_id] = task_args
    return task_dict


def build_task(param_dictionary, task_id: str) -> TaskArgs:
    raw_task_args: RawTaskParams = param_dictionary["tasks"][task_id]
    stim_args: StimulusArgs = param_dictionary["stimuli"][raw_task_args.stimulus_id]
    task_constructor = stim_args.stimulus_file
    instr_args: Optional[InstructionArgs] = None
    arg_parser: str = raw_task_args.arg_parser
    feature_of_interest: str = raw_task_args.feature_of_interest
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
        device_args=device_args,
        arg_parser=arg_parser,
        feature_of_interest=feature_of_interest
    )
    return task_args
