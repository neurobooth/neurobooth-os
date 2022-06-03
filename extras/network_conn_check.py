# -*- coding: utf-8 -*-
"""
Created on Tue Mar 22 18:27:46 2022

@author: ACQ
"""

import subprocess
import os
import datetime
import time

def write_file(msg, this_node):
    fname = f"socket_activity_{this_node}.txt"
    with open(fname, 'a') as fp:
        datestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fp.write(f'{datestamp} {msg}')

this_node = 'acq'
nodes = ['ctr', 'stm', 'acq']   

while True:
    for node in nodes:   
    
        out = subprocess.run(['ping', node], stdout=subprocess.PIPE)
        out_prt = out.stdout.decode('utf-8')
        if "request timed out" in out_prt or '(0% loss)' not in out_prt:
            print(out_prt)
            write_file(out_prt, this_node)
    
    # time.sleep(10)