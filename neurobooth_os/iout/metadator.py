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
            'neurodoor.nmr.mgh.harvard.edu',
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


def get_subj_ids(conn):
    table_subject = Table('subject', conn=conn)
    subjects_df = table_subject.query('SELECT * from subject')
    subject_ids = subjects_df.index.values.tolist()  # for autocomplete
    return subject_ids


def get_study_ids(conn):
    table_study = Table('study', conn=conn)
    studies_df = table_study.query('SELECT * from study')
    study_ids = studies_df.index.values.tolist()
    return study_ids


def get_collection_ids(study_id, conn):
    table_study = Table('study', conn=conn)
    studies_df = table_study.query('SELECT * from study')
    collection_ids = studies_df.loc[study_id, "collection_ids"]
    return collection_ids


def get_tasks(collection_id, conn):
    table_collection = Table('collection', conn=conn)
    collection_df = table_collection.query(
        f"SELECT * from collection WHERE collection_id = '{collection_id}'")
    tasks_ids, = collection_df["tech_obs_array"]
    return tasks_ids

def _new_tech_log_dict(application_id="neurobooth_os"):
    tech_obs_log = OrderedDict()
    tech_obs_log["subject_id"] = ""
    tech_obs_log["study_id"] = ""
    tech_obs_log["tech_obs_id"] = ""
    tech_obs_log["staff_id"] = ""
    tech_obs_log["application_id"] = "neurobooth_os"
    tech_obs_log["date_times"] = '{'+ datetime.now().strftime("%Y-%m-%d %H:%M:%S") + '}'
    tech_obs_log["event_array"] = []  # marker_name:timestamp
    tech_obs_log["collection_id"] = ""
    return tech_obs_log

def get_tech_obs_logs(conn):
    table_tech_obs_log = Table("tech_obs_log", conn=conn)
    tech_obs = table_tech_obs_log.query("SELECT * from tech_obs_log")
    return tech_obs

def _make_new_tech_obs_row(conn, subject_id):
    table = Table("tech_obs_log", conn=conn)
    return table.insert_rows([(subject_id,)], cols=['subject_id'])

def _fill_tech_obs_row(tech_obs_id, dict_vals, conn):
    # tech_obs_id = str
    # dict_vals = dict with key-vals to fill row
    table = Table("tech_obs_log", conn=conn)
    vals = list(dict_vals.values())
    table.update_row(tech_obs_id, tuple(vals), cols=list(dict_vals))
    
def get_sens_file_logs(conn):
    table_sens_log = Table("sensor_file_log", conn=conn)
    sens_log = table_sens_log.query("SELECT * from sensor_file_log")
    return sens_log
 
def make_new_sess_log_id():
    conn = get_conn()
    sens_log = get_sens_file_logs(conn)
    if list(sens_log.index) == []:
        sens_id = "sens_log_1"
    else:
        sens_id_last = sens_log.index[-1]
        num = int(sens_id_last.split("_")[-1])
        sens_id = f"sens_log_{num + 1}"
    return sens_id

def _get_task_param(obs_id, conn):
    table_tech_obs = Table('tech_obs_data', conn=conn)
    tech_obs_df = table_tech_obs.query(
        f"SELECT * from tech_obs_data WHERE tech_obs_id = '{obs_id}'")
    devices_ids, = tech_obs_df["device_id_array"]
    sens_ids, = tech_obs_df["sensor_id_array"]
    stimulus_id, = tech_obs_df["stimulus_id"]
    instr_id,  =  tech_obs_df["instruction_id"]
    instr_kwargs = _get_instruct_dic_param(instr_id, conn)
    return stimulus_id, devices_ids, sens_ids, instr_kwargs

def _get_instruct_dic_param(instruction_id, conn):
    if instruction_id is None:
        return {}
    table = Table('instruction', conn=conn)
    instr = table.query(f"SELECT * from instruction WHERE instruction_id = '{instruction_id}'")
    dict_instr = instr.iloc[0].to_dict()
    #remove unnecessary fields
    _ = [dict_instr.pop(l) for l in ['is_active', 'date_created', 'version', 'assigned_tech_obs']]
    return dict_instr


def _get_task_stim(stimulus_id, conn):
    table_stimulus = Table('stimulus', conn)
    stimulus_df = table_stimulus.query(
        f"SELECT * from stimulus WHERE stimulus_id = '{stimulus_id}'")
    stim_file, = stimulus_df["stimulus_file"]

    taks_kwargs = {"duration": stimulus_df['duration'][0],
                    'num_iterations':stimulus_df['num_iterations'][0]}


    # Load args from jason if any
    stim_fparam, = stimulus_df["parameters_file"]
    if stim_fparam is not None:
        dirpath =  op.split(neurobooth_os.__file__)[0]
        with open(op.join(dirpath, stim_fparam.replace('./', '')), 'rb') as f:
            parms = json.load(f)
        taks_kwargs.update(parms)

    return stim_file, taks_kwargs


def get_sens_param(sens_id, conn):
    table_sens = Table('sensor', conn=conn)
    tech_obs_df = table_sens.query(
        f"SELECT * from sensor WHERE sensor_id = '{sens_id}'")
    param = tech_obs_df.iloc[0].to_dict()
    return param


def get_dev_sn(dev_id, conn):
    table_sens = Table('device', conn=conn)
    device_df = table_sens.query(
        f"SELECT * from device WHERE device_id = '{dev_id}'")
    sn = device_df["device_sn"]
    if len(sn) == 0:
        return None
    return sn[0]


def meta_devinfo_tofunct(dev_id_param, dev_id):
    # Convert SN and sens param from metadata to kwarg for device function
    # input: dict, from get_kwarg_task
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
        print(f"Device id parameters not found for {dev_id} in meta_devinfo_tofunct")

    return kwarg


def get_kwarg_task(task_id, conn):

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
            dev_id_param["sensors"][sens_id] = get_sens_param(sens_id, conn)

        kwarg = meta_devinfo_tofunct(dev_id_param, dev_id)

        dev_kwarg[dev_id] = kwarg
    return dev_kwarg


def _get_coll_dev_kwarg_tasks(collection_id, conn):
    # Get devices kwargs for all the tasks
    # outputs dict with keys = stimulus_id, vals = dict with dev parameters

    tech_obs = get_tasks(collection_id, conn)

    tasks_kwarg = OrderedDict()
    for task in tech_obs:
        stim_id, *_ = _get_task_param(task, conn)
        task_kwarg = get_kwarg_task(task, conn)
        tasks_kwarg[stim_id] = task_kwarg

    return tasks_kwarg


def get_new_dev_param(kwarg_task1, kwarg_task2):
    # change device and device parameters between tasks
    # TODO test kwarg_task from get_coll_dev_kwarg_tasks(collection_id)

    open_dev = []
    close_dev = []
    change_param = {}
    for k1, v1 in kwarg_task1.items():
        # dev not present in task2
        if not kwarg_task2.get(k1):
            close_dev.append(k1)
            # print("close", k1)
            continue

        # dev parameters change
        if not v1 == kwarg_task2.get(k1):
            v2 = kwarg_task2.get(k1)
            # print(v1)
            change_param[k1] = {}
            for kk1, vv1 in v1.items():
                if vv1 != v2.get(kk1):
                    change_param[k1]["vv1"] = v2.get(kk1)
                    # print(kk1, vv1, v2.get(kk1))

    for k2, v2 in kwarg_task2.items():
        # print(k1, v1)
        if not kwarg_task1.get(k2):
            open_dev.append(k2)
            # print(k2)

    return open_dev, close_dev, change_param
