# -*- coding: utf-8 -*-
"""
Created on Thu Mar 25 12:46:08 2021

@author: neurobooth
"""

# from registration import get_session_info
import os
import socket
import time
import psutil

import numpy as np

from neurobooth_os import config
from neurobooth_os.netcomm import socket_message, socket_time, start_server, kill_pid_txt


def _get_nodes(nodes):
    if isinstance(nodes, str):
        nodes = (nodes)
    return nodes


def start_servers(nodes=("acquisition", "presentation"), remote=False, conn=None):
    """Start servers

    Parameters
    ----------
    nodes : tuple, optional
        The nodes at which to start server, by default ("acquisition", "presentation")
    remote : bool, optional
        If True, start fake servers, by default False
    conn : callable, mandatory if remote True
        Connector to the database, used if remote True
    """
    if remote:
        from neurobooth_os.mock import mock_server_stm, mock_server_acq
        _ = mock_server_acq(conn)
        _ = mock_server_stm(conn)
    else:
        kill_pid_txt()
        nodes = _get_nodes(nodes)
        for node in nodes:
            start_server(node)


def prepare_feedback(nodes=("acquisition", "presentation")):
    nodes = _get_nodes(nodes)
    for node in nodes:
        if node.startswith("acq"):
            msg = "vis_stream"
        elif node.startswith("pres"):
            msg = "scr_stream"
        else:
            return
    socket_message(msg, node)
    

def prepare_devices(collection_id="mvp_025", nodes=("acquisition", "presentation")):
    # prepares devices, collection_id can be just colletion name but also
    # "collection_id:str(tech_obs_log)"
    nodes = _get_nodes(nodes)
    for node in nodes:
        socket_message(f"prepare:{collection_id}", node)

    
def shut_all(nodes=("acquisition", "presentation")):
    """Shut all nodes

    Parameters
    ----------
    nodes : tuple | str
        The node names
    """
    nodes = _get_nodes(nodes)
    for node in nodes:
        socket_message("shutdown", node)
    kill_pid_txt()  # TODO only if error


def test_lan_delay(n=100, nodes=("acquisition", "presentation")):
    """Test LAN delay

    Parameters
    ----------
    n : int
        The number of iterations
    nodes : tuple | str
        The node names
    """
    nodes = _get_nodes(nodes)
    times_1w, times_2w = [], []

    for node in nodes:
        tmp = []
        for i in range(n):
            tmp.append(socket_time(node, 0))
        times_1w.append([t[1] for t in tmp])
        times_2w.append([t[0] for t in tmp])

    _ = [print(f"{n} socket connexion time average:\n\t receive: {np.mean(times_2w[i])}\n\t send:\t  {np.mean(times_1w[i])} ")
         for i, n in enumerate(nodes)]

    return times_2w, times_1w


def initiate_labRec():
    # Start LabRecorder
    if "LabRecorder.exe" not in (p.name() for p in psutil.process_iter()):
        os.startfile(config.paths['LabRecorder'])

    time.sleep(.05)
    s = socket.create_connection(("localhost", 22345))
    s.sendall(b"select all\n")
    s.close()


if 0:
    pid = start_server('acquisition')

    socket_message("connect_mbient", "acquisition")
    socket_message("shutdown", "acquisition")

    t2w, t1w = test_lan_delay(100)

    prepare_feedback()

    prepare_devices()

    task_name = "timing_task"
    task_presentation(task_name, "filename")
