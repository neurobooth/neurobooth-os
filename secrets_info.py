# -*- coding: utf-8 -*-
"""
Created on Wed Apr  7 14:41:23 2021

@author: neurobooth
"""

        
        
acquisition = {'name': 'acq',
               'user': 'ACQ',
               'pass': "5519",
               "bat" : r'C:\neurobooth-eel\serv_acq.bat'                      
               }

presentation = {'name': 'stm',
               'user': 'STM',
               'pass': "5519",
               "bat" : r'C:\neurobooth-eel\server_stm.bat'                       
               }
    
secrets = {'acquisition' : acquisition, 
           'presentation': presentation}