# -*- coding: utf-8 -*-
"""
Created on Wed Apr  7 14:41:23 2021

@author: neurobooth
"""

        
        
acquisition = {'name': 'acq',
               'user': 'ACQ',
               'pass': "5519",
               "bat" : r'C:\neurobooth-eel\neurobooth-os\serv_acq.bat'                      
               }

presentation = {'name': 'stm',
               'user': 'STM',
               'pass': "5519",
               "bat" : r'C:\neurobooth-eel\neurobooth-os\server_stm.bat'                       
               }
    
secrets = {'acquisition' : acquisition, 
           'presentation': presentation}

db_secrets = {"connect_str" : ("dbname='neurobooth' user='neuroboother' host='192.168.100.1' "
               "password='neuroboothrocks'")}