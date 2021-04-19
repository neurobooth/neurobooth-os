# -*- coding: utf-8 -*-
"""
Created on Wed Mar 31 12:21:06 2021

@author: Adonay
"""

import socket 
from time import time  

  
def server_com(callback=None):  
    port = 12347
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", port)) 
    print("Ctr socket binded to port", port) 
  
    s.listen(5) 
    print("socket is listening") 
    
    while True: 
        c, addr = s.accept() 
        data = c.recv(1024)
        if not data: 
            print("Connection fault, closing ctr server")
            break

        data = data.decode("utf-8")
        print(data)
        
        if callback is not None:
            callback(data)

        if "record_start" in data:  #-> "record:FILENAME"
            fname = data.split(":")[-1]            
            print(f"Starting recording {fname}")
            
        elif "record_stop" in data:                        
            print("Closing recording")
            break
        
        elif "time_test" in data:
            msg = f"ping_{time()}"
            c.send(msg.encode("ascii"))                     
            
    s.close() 
  
  
def test(callback):
    for i in range(10):
        callback(i)
        print(i)