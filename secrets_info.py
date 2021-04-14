# -*- coding: utf-8 -*-
"""
Created on Wed Apr  7 14:41:23 2021

@author: neurobooth
"""


        
        
acquisition = {'name':  '192.168.1.7',
               'user': 'ACQ',
               'pass': "5519",
               "bat" : r'C:\neurobooth\neurobooth-eel\serv_acq.bat'   
                      
               }

presentation = {'name':  '192.168.1.5',
               'user': 'adona',
               'pass': "Cleo1234!",
               "bat" : r'C:\Users\adona\OneDrive\Desktop\neurobooth\neurobooth-eel\server_stm.bat'
                         
               }
    
secrets = {'acquisition' : acquisition, 
           'presentation': presentation}