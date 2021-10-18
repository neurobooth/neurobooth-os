# -*- coding: utf-8 -*-
"""
Created on Wed Apr  7 14:41:23 2021

@author: Adonay Nunes 
"""
import os.path as op
from os.path import expanduser
import json
import neurobooth_os

fname = op.join(expanduser("~"), ".neurobooth_os_secrets")
if not op.exists(fname):
    pakg_path = neurobooth_os.__path__[0]
    secrets = {
        'acquisition' : {
            'name': 'acq',
            'user': 'ACQ',
            'pass': "",
            "bat" : op.join(pakg_path, 'serv_acq.bat')
        },
        'presentation': {
            'name': 'stm',
            'user': 'STM',
            'pass': "",
            "bat" : op.join(pakg_path, 'serv_acq.bat')
            },
        'database':{
            "dbname" : 'neurobooth',
            'user':'neuroboother',
            'pass': "",
            'host':'192.168.100.1',
            'remote_username': 'ab123'
            }
        }
    with open(fname, "w+") as f:
        json.dump(secrets, f, ensure_ascii=False, indent=4)

with open(fname, 'r') as f:
    secrets = json.load(f)





