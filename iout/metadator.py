# -*- coding: utf-8 -*-
"""
Created on Fri Jul 30 09:08:53 2021

@author: CTR
"""

from neurobooth_terra import list_tables, create_table, drop_table, Table
import psycopg2
import pandas as pd


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
    devices, = tech_obs_df[ "device_id_array"]
    devices_param, = tech_obs_df[ "sensor_id_array"] 
    stimulus_id, = tech_obs_df["stimulus_id"]
    return stimulus_id, devices, devices_param
    
def get_task_stim(stimulus_id, conn):
    table_stimulus = Table('stimulus', conn)   
    stimulus_df = table_stimulus.query(
        f"SELECT * from stimulus WHERE stimulus_id = '{stimulus_id}'")
    stim_file = stimulus_df["stimulus_file"]
    stim_fparam = stimulus_df["parameters_file"]
    return stim_file, stim_fparam
    
