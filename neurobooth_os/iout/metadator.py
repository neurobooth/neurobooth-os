# -*- coding: utf-8 -*-
"""
Created on Fri Jul 30 09:08:53 2021

@author: CTR
"""

from neurobooth_terra import list_tables, create_table, drop_table, Table
import psycopg2
import pandas as pd
import json
from collections import OrderedDict


def get_conn():
    connect_str = ("dbname='neurobooth' user='neuroboother' host='192.168.100.1' "
               "password='neuroboothrocks'")
    conn = psycopg2.connect(connect_str)
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
    
def get_tech_obs_logs(conn):
    table_tech_obs_log = Table("tech_obs_log", conn=conn)
    tech_obs = table_tech_obs_log.query("SELECT * from tech_obs_log")
    return tech_obs

def make_new_tech_obs_id():
    conn = get_conn()
    tech_obs = get_tech_obs_logs(conn)
    if list(tech_obs.index) == []:
        tech_id = "session_log_1"
    else:
        tech_id_last = tech_obs.index[-1]
        num = int(tech_id_last.split("_")[-1])
        tech_id = f"session_log_{num + 1}"
    return tech_id
    

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
    
def get_task_param(task_id, conn):
    table_tech_obs = Table('tech_obs_data', conn=conn)
    tech_obs_df = table_tech_obs.query(
        f"SELECT * from tech_obs_data WHERE tech_obs_id = '{task_id}'")
    devices_ids, = tech_obs_df[ "device_id_array"]
    sens_ids, = tech_obs_df[ "sensor_id_array"] 
    
    stimulus_id, = tech_obs_df["stimulus_id"]
    return stimulus_id, devices_ids, sens_ids
    
def get_task_stim(stimulus_id, conn):
    table_stimulus = Table('stimulus', conn)   
    stimulus_df = table_stimulus.query(
        f"SELECT * from stimulus WHERE stimulus_id = '{stimulus_id}'")
    stim_file, = stimulus_df["stimulus_file"]
    stim_fparam, = stimulus_df["parameters_file"]
    return stim_file, stim_fparam
    
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
    if "Intel" in dev_id:        
        kwarg["camindex"] = [int(dev_id[-1]), info["SN"]]
               
        for k in info['sensors'].keys():
            if "rgb" in k:
                size_x = int(info['sensors'][k]['spatial_res_x'])
                size_y = int(info['sensors'][k]['spatial_res_y'])
                kwarg["size_rgb"]  = (size_x, size_y)
                kwarg["fps_rgb"]  = int (info['sensors'][k]['temporal_res'])
                
            elif "depth" in k:
                size_x = int(info['sensors'][k]['spatial_res_x'])
                size_y = int(info['sensors'][k]['spatial_res_y'])
                kwarg["size_depth"]  = (size_x, size_y)
                kwarg["fps_depth"]  =  int(info['sensors'][k]['temporal_res'] )
    
    elif "Mbient" in dev_id:
         kwarg["dev_name"] = dev_id.split("_")[1]
         kwarg["mac"] = info["SN"]
         for k in info['sensors'].keys():
            if "acc" in k:
                kwarg["acc_hz"]  = int(info['sensors'][k]['temporal_res'])                
            elif "gra" in k:
                kwarg["gyro_hz"]  = int(info['sensors'][k]['temporal_res'])                

    elif "FLIR_blackfly" in dev_id:          
        kwarg["camSN"] = info["SN"]
        k, = info['sensors'].keys()
        # TODO test asserting assert(len(list(info['sensors']))==1) raise f"{dev_id} should have only one sensor"
        kwarg["fps"] = int(info['sensors'][k]['temporal_res'])
        kwarg["sizex"] = int(info['sensors'][k]['spatial_res_x'])
        kwarg["sizey"] = int(info['sensors'][k]['spatial_res_y'])
    
    elif "Mic_Yeti" in dev_id:
       # TODO test asserting assert(len(list(info['sensors']))==1) raise f"{dev_id} should have only one sensor"
         k, = info['sensors'].keys()
         kwarg["RATE"] = int(info['sensors'][k]['temporal_res'])
         kwarg["CHUNK"] = int(info['sensors'][k]['spatial_res_x'])
    
    elif "Eyelink" in dev_id:
        kwarg["ip"] = info["SN"]
       # TODO test asserting assert(len(list(info['sensors']))==1) raise f"{dev_id} should have only one sensor"
        k, = info['sensors'].keys()
        kwarg["sample_rate"] =  int(info['sensors'][k]['temporal_res'])
    else:
         print(f"Device id parameters not found for {dev_id} in meta_devinfo_tofunct")
         
    return kwarg


def get_kwarg_task(task_id, conn):
            
    stim_id, dev_ids, sens_ids = get_task_param(task_id, conn)
    
    dev_kwarg = {}
    for dev_id, dev_sens_ids in zip( dev_ids, sens_ids):
        # TODO test that dev_sens_ids are from correct dev_id, eg. dev_sens_ids =  {Intel_D455_rgb_1,Intel_D455_depth_1} dev_id= Intel_D455_x
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


def get_coll_dev_kwarg_tasks(collection_id):
    # Get devices kwargs for all the tasks
    # outputs dict with keys = stimulus_id, vals = dict with dev parameters
           
    conn =  get_conn()
    tasks = get_tasks(collection_id, conn)   
    
    tasks_kwarg = OrderedDict()
    for task in tasks:        
        stim_id, _, _ = get_task_param(task, conn)
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
            for  kk1, vv1 in v1.items():
                if vv1 != v2.get(kk1):
                    change_param[k1]["vv1"] = v2.get(kk1)
                    # print(kk1, vv1, v2.get(kk1))

    for k2, v2 in kwarg_task2.items():
        # print(k1, v1)
        if not kwarg_task1.get(k2):
            open_dev.append(k2)
            # print(k2)
            
    
    return open_dev,  close_dev, change_param
    
    
    
    