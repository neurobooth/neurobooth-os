# -*- coding: utf-8 -*-
"""
Created on Thu Mar 25 13:49:04 2021

@author: neurobooth
"""

import eel
from collections import OrderedDict

session_information = {"subject_id":"", "condition":"", "gender":"", "age":"", 
                            "rc_initials":"", "tasks":OrderedDict({"sync_test":True,
                            "dst":True, "mt":"mouse_tracking.html", "ft":True })}

def get_session_info():
    
    global session_information 
    # tasks_html_pages = {"sync_test":"synch_task.html", 
    #                     "dst":"DSC_simplified_oneProbe_2020.html", 
    #                     "mt":"mouse_tracking.html",
    #                     "ft":"task_motor_assess/motortask_instructions.html"}
    
    
    # # TODO: How decorator would be instead of cond
    # if "get_session_info" not in eel._exposed_functions.keys():
    #         del eel
    #         import eel
            
    @eel.expose
    def get_session_info(sub_id, condition, gender, age, rc_initials, 
                         check_st, check_dst, check_mt, check_ft):
        
        global session_information 
        
        session_information["subject_id"] = sub_id
        session_information["condition"] = condition
        session_information["gender"] = gender
        session_information["age"] = age
        session_information["rc_initials"] = rc_initials
        session_information["tasks"]["sync_test"] = check_st
        session_information["tasks"]["dst"] = check_dst
        session_information["tasks"]["mt"] = check_mt
        session_information["tasks"]["ft"] = check_ft
        
        return session_information
    
    
    eel.init('www', ['.js', '.html', '.jpg'])
    
    try:
        #Start the application and pass all initial params below
          eel.start('index.html', size= (1040, 1200), cmdline_args=['--kisok'], geometry={'size':  (1040, 720), 'position': (0.1, 0.3)})
    except (SystemExit):
         return session_information
          
