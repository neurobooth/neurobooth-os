# -*- coding: utf-8 -*-
"""
Created on Wed Apr  7 14:41:23 2021

@author: Adonay NUnes


Example of a scecret file containing ACQ and STM credentials and path to batch file, and credentials for the database access.
"""


acquisition = {'name': 'acq',
               'user': 'ACQ',
               'pass': "",  # ACQ user password
               "bat" : r'C:\neurobooth-eel\neurobooth_os\serv_acq.bat'
               }

presentation = {'name': 'stm',
               'user': 'STM',
               'pass': "",  # STM user password
               "bat" : r'C:\neurobooth-eel\neurobooth_os\server_stm.bat'
               }

secrets = {'acquisition' : acquisition,
           'presentation': presentation}


db_secrets = {"dbname" : 'database_name',
              'user':'user',
              'host':'192.168.100.1'
              }
