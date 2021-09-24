# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""
import time
from time import sleep
import socket
import sys
import threading
import queue

from neurobooth_os.netcomm.mock_server_stm import mock_stm_routine

from neurobooth_os import config
from neurobooth_os.iout import ScreenMirror
from neurobooth_os.iout.lsl_streamer import (start_lsl_threads, close_streams, reconnect_streams, connect_mbient)

from neurobooth_os.netcomm import socket_message, node_info, get_client_messages, get_fprint, get_messages_to_ctr)

import neurobooth_os.tasks.utils as utl
from neurobooth_os.tasks.task_importer import get_task_funcs

from neurobooth_os.iout import metadator as meta


def _make_server_ctr():
    host, port = node_info("dummy_ctr")

    data_received = queue.Queue()
    server_thread = threading.Thread(target=get_messages_to_ctr,
                                     args=(data_received, host, port,),
                                     daemon=True)
    server_thread.start()
    return server_thread, data_received


def  _make_server_stm():
    host, port = node_info("dummy_stm")

    data_received = queue.Queue()
    server_thread = threading.Thread(target=mock_stm_routine,
                                     args=(host, port,),
                                     daemon=True)
    server_thread.start()
    return server_thread, data_received


