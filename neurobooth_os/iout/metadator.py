# -*- coding: utf-8 -*-
"""
Created on Fri Jul 30 09:08:53 2021

@author: CTR
"""
import os.path as op
import json
from collections import OrderedDict
from datetime import datetime

from sshtunnel import SSHTunnelForwarder
import psycopg2
from neurobooth_terra import  Table

import neurobooth_os
from neurobooth_os.secrets_info import secrets

def get_conn(remote=False, database='neurobooth'):
    """ Gets connector to the database

    Parameters
    ----------
    remote : bool, optional
        Flag to use SSH tunneling to connect, by default False
    database : str, optional
        Name of the database, by default 'neurobooth'

    Returns
    -------
    conn : object
        connector to psycopg database
    """
    if remote:
        tunnel = SSHTunnelForwarder(
            secrets['database']['remote_address'],
            ssh_username=secrets['database']['remote_username'],
            ssh_config_file='~/.ssh/config',
            ssh_pkey='~/.ssh/id_rsa',
            remote_bind_address=(secrets['database']['host'], 5432),
            local_bind_address=('localhost', 6543))
        tunnel.start()
        host = tunnel.local_bind_host
        port = tunnel.local_bind_port
    else:
        host = secrets['database']['host']
        port = 5432
    conn = psycopg2.connect(database=database, 
                            user=secrets['database']['user'],
                            password=secrets['database']['pass'],
                            host=host,
                            port=port)
    return conn


def get_study_ids(conn):
    table_study = Table('study', conn=conn)
    studies_df = table_study.query()
    study_ids = studies_df.index.values.tolist()
    return study_ids


def get_subject_ids(conn, first_name, last_name):
    table_subject = Table('subject', conn=conn)
    subject_df = table_subject.query(
        where=f"LOWER(first_name_birth)=LOWER('{first_name}') AND LOWER(last_name_birth)=LOWER('{last_name}')")
    return subject_df


def get_collection_ids(study_id, conn):
    table_study = Table('study', conn=conn)
    studies_df = table_study.query()
    collection_ids = studies_df.loc[study_id, "collection_ids"]
    return collection_ids


def get_tasks(collection_id, conn):
    table_collection = Table('collection', conn=conn)
    collection_df = table_collection.query(where=f"collection_id = '{collection_id}'")
    tasks_ids, = collection_df["tech_obs_array"]
    return tasks_ids


def _new_tech_log_dict(application_id="neurobooth_os"):
    """Create a new tech_obs_log dict."""
    tech_obs_log = OrderedDict()
    tech_obs_log["subject_id"] = ""
    tech_obs_log["study_id"] = ""
    tech_obs_log["tech_obs_id"] = ""
    tech_obs_log["staff_id"] = ""
    tech_obs_log["application_id"] = "neurobooth_os"
    tech_obs_log["date_times"] = '{'+ datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '}'
    tech_obs_log["event_array"] = []  # marker_name:timestamp
    tech_obs_log["collection_id"] = ""
    return tech_obs_log  # XXX: tech_obs_log_dict


def _make_new_tech_obs_row(conn, subject_id):
    table = Table("tech_obs_log", conn=conn)
    return table.insert_rows([(subject_id,)], cols=['subject_id'])


def _fill_tech_obs_row(tech_obs_id, dict_vals, conn):  # XXX: dict_vals -> tech_obs_log_dict
    # tech_obs_id = str
    # dict_vals = dict with key-vals to fill row
    table = Table("tech_obs_log", conn=conn)
    vals = list(dict_vals.values())
    table.update_row(tech_obs_id, tuple(vals), cols=list(dict_vals))


def _get_task_param(tech_obs_id, conn):
    """Get .
    
    obs_id : str
        The tech_obs_id
    """
    # tech_obs_data, stimulus, instruction
    table_tech_obs = Table('tech_obs_data', conn=conn)
    tech_obs_df = table_tech_obs.query(where=f"tech_obs_id = '{tech_obs_id}'")
    devices_ids, = tech_obs_df["device_id_array"]
    sens_ids, = tech_obs_df["sensor_id_array"]
    stimulus_id, = tech_obs_df["stimulus_id"]
    instr_id,  =  tech_obs_df["instruction_id"]
    instr_kwargs = _get_instruction_kwargs(instr_id, conn)
    #  stim_file, stim_kwargs = meta._get_task_stim(task_stim_id, conn)
    # task = {'instruction_kwargs': dict(), 'stimulus_kwargs': dict(), 'device_ids': ..., } ?
    return stimulus_id, devices_ids, sens_ids, instr_kwargs  # XXX: name similarly in calling function


def _get_instruction_kwargs(instruction_id, conn):
    """Get dictionary from instruction table."""
    if instruction_id is None:
        return {}
    table = Table('instruction', conn=conn)
    instr = table.query(where=f"instruction_id = '{instruction_id}'")
    dict_instr = instr.iloc[0].to_dict()
    #remove unnecessary fields
    _ = [dict_instr.pop(l) for l in ['is_active', 'date_created', 'version', 'assigned_tech_obs']]
    return dict_instr


def _get_stimulus_kwargs(stimulus_id, conn):
    """Get task parameters from database."""
    table_stimulus = Table('stimulus', conn)
    stimulus_df = table_stimulus.query(where=f"stimulus_id = '{stimulus_id}'")
    stim_file, = stimulus_df["stimulus_file"]

    taks_kwargs = {"duration": stimulus_df['duration'][0],
                    'num_iterations':stimulus_df['num_iterations'][0]}

    if not stimulus_df['parameters'].isnull().all():
        params = stimulus_df['parameters'].values[0]
        taks_kwargs.update(params)

    # Load args from jason if any
    stim_fparam, = stimulus_df["parameters_file"]
    if stim_fparam is not None:
        dirpath =  op.split(neurobooth_os.__file__)[0]
        with open(op.join(dirpath, stim_fparam.replace('./', '')), 'rb') as f:
            parms = json.load(f)
        taks_kwargs.update(parms)

    return stim_file, taks_kwargs


def _get_sensor_kwargs(sens_id, conn):
    table_sens = Table('sensor', conn=conn)
    tech_obs_df = table_sens.query(where=f"sensor_id = '{sens_id}'")
    param = tech_obs_df.iloc[0].to_dict()
    return param


def get_dev_sn(dev_id, conn):
    table_sens = Table('device', conn=conn)
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
    kwarg["sensor_ids"] = list(info['sensors'])

    if "mock_Mbient" in dev_id:
        kwarg["name"] = dev_id
        k = list(info['sensors'])[0]
        kwarg['srate'] = int(info['sensors'][k]['temporal_res'])

    elif "mock_Intel" in dev_id:
        kwarg["name"] = dev_id
        k = list(info['sensors'])[0]
        kwarg['srate'] = int(info['sensors'][k]['temporal_res'])
        kwarg['sizex'] = int(info['sensors'][k]['spatial_res_x'])
        kwarg['sizey'] = int(info['sensors'][k]['spatial_res_y'])

    elif "Intel" in dev_id:
        kwarg["camindex"] = [int(dev_id[-1]), info["SN"]]

        for k in info['sensors'].keys():
            if "rgb" in k:
                size_x = int(info['sensors'][k]['spatial_res_x'])
                size_y = int(info['sensors'][k]['spatial_res_y'])
                kwarg["size_rgb"] = (size_x, size_y)
                kwarg["fps_rgb"] = int(info['sensors'][k]['temporal_res'])

            elif "depth" in k:
                size_x = int(info['sensors'][k]['spatial_res_x'])
                size_y = int(info['sensors'][k]['spatial_res_y'])
                kwarg["size_depth"] = (size_x, size_y)
                kwarg["fps_depth"] = int(info['sensors'][k]['temporal_res'])

    elif "Mbient" in dev_id:
        kwarg["dev_name"] = dev_id.split("_")[1]
        kwarg["mac"] = info["SN"]
        for k in info['sensors'].keys():
            if "acc" in k:
                kwarg["acc_hz"] = int(info['sensors'][k]['temporal_res'])
            elif "gra" in k:
                kwarg["gyro_hz"] = int(info['sensors'][k]['temporal_res'])

    elif "FLIR_blackfly" in dev_id:
        kwarg["camSN"] = info["SN"]
        k, = info['sensors'].keys()
        # TODO test asserting assert(len(list(info['sensors']))==1) raise
        # f"{dev_id} should have only one sensor"
        kwarg["fps"] = int(info['sensors'][k]['temporal_res'])
        kwarg["sizex"] = int(info['sensors'][k]['spatial_res_x'])
        kwarg["sizey"] = int(info['sensors'][k]['spatial_res_y'])

    elif "Mic_Yeti" in dev_id:
       # TODO test asserting assert(len(list(info['sensors']))==1) raise
       # f"{dev_id} should have only one sensor"
        k, = info['sensors'].keys()
        kwarg["RATE"] = int(info['sensors'][k]['temporal_res'])
        kwarg["CHUNK"] = int(info['sensors'][k]['spatial_res_x'])

    elif "Eyelink" in dev_id:
        kwarg["ip"] = info["SN"]
       # TODO test asserting assert(len(list(info['sensors']))==1) raise
       # f"{dev_id} should have only one sensor"
        k, = info['sensors'].keys()
        kwarg["sample_rate"] = int(info['sensors'][k]['temporal_res'])
    elif "Mouse" in dev_id:
        return kwarg
    else:
        print(f"Device id parameters not found for {dev_id} in map_database_to_deviceclass")

    return kwarg


def _get_device_kwargs(task_id, conn):

    stim_id, dev_ids, sens_ids, _ = _get_task_param(task_id, conn)
    dev_kwarg = {}
    for dev_id, dev_sens_ids in zip(dev_ids, sens_ids):
        # TODO test that dev_sens_ids are from correct dev_id, eg. dev_sens_ids =
        # {Intel_D455_rgb_1,Intel_D455_depth_1} dev_id= Intel_D455_x
        dev_id_param = {}
        dev_id_param["SN"] = get_dev_sn(dev_id, conn)

        dev_id_param["sensors"] = {}

        for sens_id in dev_sens_ids:
            if sens_id == "":
                continue
            dev_id_param["sensors"][sens_id] = _get_sensor_kwargs(sens_id, conn)

        kwarg = map_database_to_deviceclass(dev_id, dev_id_param)

        dev_kwarg[dev_id] = kwarg
    return dev_kwarg


def _get_device_kwargs_by_task(collection_id, conn):
    # Get devices kwargs for all the tasks
    # outputs dict with keys = stimulus_id, vals = dict with dev parameters

    tech_obs = get_tasks(collection_id, conn)

    tasks_kwarg = OrderedDict()
    for task in tech_obs:
        stim_id, *_ = _get_task_param(task, conn)
        task_kwarg = _get_device_kwargs(task, conn)
        tasks_kwarg[stim_id] = task_kwarg

    return tasks_kwarg



# List of functions
# -----------------
#
# get_conn
#
# Create functions
# ~~~~~~~~~~~~~~~~
# _new_tech_log_dict ?
# _make_new_tech_obs_row
# 
# Read functions
# ~~~~~~~~~~~~~~
# get_study_ids
# get_subject_ids
# get_collection_ids
# get_tasks
# get_dev_sn
# _get_task_param(tech_obs_id)
# _get_instruction_kwargs(instruction_id)
# _get_stimulus_kwargs(stimulus_id)
# _get_device_kwargs_by_task(collection_id)
# _get_device_kwargs(tech_obs_id)
# _get_sensor_kwargs(sensor_id)
# map_database_to_deviceclass(device_id, sensor_kwargs)
#
# Update functions
# ~~~~~~~~~~~~~~~~
# _fill_tech_obs_row

