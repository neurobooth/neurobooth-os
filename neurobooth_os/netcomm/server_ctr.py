# -*- coding: utf-8 -*-
"""
Created on Wed Mar 31 12:21:06 2021

@author: Adonay
"""

import socket
from time import time


def server_com(qu=None, host="", port=12347):

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", port))
    print("Ctr socket binded to port", port)

    s.listen(5)
    print("socket is listening")

    while True:
        try:
            c, addr = s.accept()
            data = c.recv(1024)
        except BaseException:
            print("Connection fault, closing ctr server")
            continue

        data = data.decode("utf-8")
        print(data)

        if qu is not None:
            qu.put(data)

        if data == "close":
            break
    s.close()
