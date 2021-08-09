# -*- coding: utf-8 -*-
"""
Created on Fri Jul 30 09:08:53 2021

@author: CTR
"""

from neurobooth_terra import list_tables, create_table, drop_table, Table
import psycopg2
import pandas as pd
import json

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
        f"SELECT * from collection WHERE collection_name = '{collection_id}'")
    tasks_ids, = collection_df["tech_obs_array"]
    return tasks_ids
    

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
    stim_file = stimulus_df["stimulus_file"]
    stim_fparam = stimulus_df["parameters_file"]
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
    sn, = device_df["device_sn"]
    return sn


def db_devinfo_tofunct(dev_dic, key):
    # get dev and sensor info from DB and convert to arg funct
    # input: dev_dic = {key: {"SN": str,
    #                       "sensors": {"sensor1": {},
    #                               "sensor2: {}
    #                        }}
    
    info = dev_dic[key]
    kwarg = { }
    if "Intel" in key:        
        kwarg["camindex"] = [int(key[-1]), info["SN"]]
               
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
            
        return kwarg
    
    elif "Mbient" in key:
         kwarg["dev_name"] = key.split("_")[1]
         kwarg["mac"] = info["SN"]
         for k in info['sensors'].keys():
            if "acc" in k:
                kwarg["acc_hz"]  = int(info['sensors'][k]['temporal_res'])                
            elif "gra" in k:
                kwarg["gyro_hz"]  = int(info['sensors'][k]['temporal_res'])                
         return kwarg

    elif "FLIR_blackfly" in key:        
        kwarg["camSN"] = info["SN"]
        k, = info['sensors'].keys()
        kwarg["fps"] = int(info['sensors'][k]['temporal_res'])
        kwarg["sizex"] = int(info['sensors'][k]['spatial_res_x'])
        kwarg["sizey"] = int(info['sensors'][k]['spatial_res_y'])
        return kwarg
                 
                 

def get_kwarg_collection(collection_id):
            
    conn =  get_conn()
    collection_id = "mvp_025"
    tasks = get_tasks(collection_id, conn)
    stim_id, dev_ids, sens_ids = get_task_param(tasks[0], conn)
    
    dev_infos = {}
    dev_kwarg = {}
    for dev_id, dev_sens_ids in zip( dev_ids, sens_ids):
        dev_infos[dev_id] = {}
        dev_infos[dev_id]["SN"] = get_dev_sn(dev_id, conn) 
        
        dev_infos[dev_id]["sensors"] = {}
            
        for sens_id in dev_sens_ids:
            if sens_id == "":
                continue
            dev_infos[dev_id]["sensors"][sens_id] = get_sens_param(sens_id, conn)
    
        kwarg = db_devinfo_tofunct(dev_infos, dev_id)
        
        dev_kwarg[dev_id] = kwarg           
    return dev_kwarg


