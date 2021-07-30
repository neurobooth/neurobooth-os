# -*- coding: utf-8 -*-
"""
Created on Fri Jul 30 09:08:53 2021

@author: CTR
"""

from neurobooth_terra import list_tables, create_table, drop_table, Table
import psycopg2
import pandas as pd


COLLECTION_NAME = "mvp_025"

connect_str = ("dbname='neurobooth' user='neuroboother' host='192.168.100.1' "
               "password='neuroboothrocks'")

conn = psycopg2.connect(connect_str)

table_id = 'collection'
table = Table(table_id, conn)
# print(table)
df = table.query(f'SELECT * FROM "{table_id}";')

tasks_id = df.loc[COLLECTION_NAME, "tech_obs_array"]
print("tasks_id:\n\t", tasks_id)

table_id = "tech_obs_data"
table = Table(table_id, conn)
# print(table)
df = table.query(f'SELECT * FROM "{table_id}";')

tasks_inf= df.loc[tasks_id]
print("tasks_inf:\n\t", tasks_inf)
stim_info = tasks_inf["stimulus_id"]


table_id = "stimulus"
table = Table(table_id, conn)
# print(table)
df = table.query(f'SELECT * FROM "{table_id}";')

stim_fname = df.loc[stim_info, "stimulus_file"]
stim_json = df.loc[stim_info, "parameters_file"]
print("stim_fname:\n\t", stim_fname)
print("stim_json:\n\t", stim_json)
