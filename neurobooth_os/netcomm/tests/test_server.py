# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""
import time
import socket
import threading
import queue

from neurobooth_os.netcomm.server import get_fprint
from neurobooth_os.netcomm.server_ctr import server_com
from neurobooth_os.netcomm.client import node_info, socket_message


def _make_server_ctr():
    host, port = node_info("dummy_ctr")

    data_received = queue.Queue()
    server_thread = threading.Thread(target=server_com,
                                     args=(data_received, host, port,),
                                     daemon=True)
    server_thread.start()
    return server_thread, data_received


def test_server_send_message():
    """ Test message sent to dummy_ctr """
    server_thread, data_received = _make_server_ctr()

    # Test socket_message
    message = "test_test"
    socket_message(message=message, node_name="dummy_ctr")
    time.sleep(1.)
    assert data_received.get(timeout=2) == message

    # Test fprint_flush
    current_node = 'dummy_client'
    fprint_flush, old_stdout = get_fprint(current_node, 'dummy_ctr')
    message = "fprint msg"
    fprint_flush(message)
    data_recv = data_received.get(timeout=2)
    assert data_recv == f'{current_node}: {message}\n '

    # kill the server_com thread
    message = "close"
    socket_message(message=message, node_name="dummy_ctr")
