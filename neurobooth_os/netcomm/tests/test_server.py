# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""
import time
import queue
import sys

from neurobooth_os.netcomm import socket_message, NewStdout
from neurobooth_os.mock import mock_server_ctr


def test_socket_message_to_ctr():
    """ Test message sent to dummy_ctr """

    data_queue = queue.Queue()
    def callback(data, data_queue):
        data_queue.put(data)
    server_thread = mock_server_ctr(callback, data_queue)

    # Test socket_message
    message = "test:::test_test"
    socket_message(message=message, node_name="dummy_ctr")
    time.sleep(1.)
    assert data_queue.get(timeout=2) == message

    # kill the server_com thread
    message = "close"
    socket_message(message=message, node_name="dummy_ctr")


def test_stdout_print_to_ctr():
    """ Test std rerouted to sent message to dummy_ctr """

    data_queue = queue.Queue()
    def callback(data, data_queue):
        data_queue.put(data)
    server_thread = mock_server_ctr(callback, data_queue)

    # Test message is received by dummy_ctr server
    sys.stdout = NewStdout("STM", target_node="dummy_ctr", terminal_print=False)
    message = "test_test2"
    queue_msg = data_queue.get(timeout=1)
    assert(queue_msg.split(":::")[1] == message)
    sys.stdout = sys.stdout.terminal

    # kill the server_thread thread
    message = "close"
    socket_message(message=message, node_name="dummy_ctr")