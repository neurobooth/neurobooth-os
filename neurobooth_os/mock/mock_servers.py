# -*- coding: utf-8 -*-
"""
Created on Tue Sep 14 15:33:40 2021

@author: adona
"""

from time import sleep
import threading
import queue

from neurobooth_os.mock.mock_server_stm import mock_stm_routine
from neurobooth_os.mock.mock_server_acq import mock_acq_routine
from neurobooth_os.netcomm import node_info, get_messages_to_ctr


def mock_server_ctr(callback, callback_args):
    """Make fake control server.

    Parameters
    ----------
    callback : callable
        function to run inside the socket data listening loop
    callback_args : callable
        arguments for the callback function

    Returns
    -------
    thread instance
    """

    host, port = node_info("dummy_ctr")
    server_thread = threading.Thread(
        target=get_messages_to_ctr,
        args=(
            callback,
            host,
            port,
            callback_args,
        ),
        daemon=True,
    )
    server_thread.start()
    return server_thread


def mock_server_stm(conn):
    """Make fake stm server.

    Parameters
    ----------
    conn : object
        Connector to the database

    Returns
    -------
    thread instance
        the instance of the server
    """

    host, port = node_info("dummy_stm")

    server_thread = threading.Thread(
        target=mock_stm_routine,
        args=(
            host,
            port,
            conn,
        ),
        daemon=True,
    )
    server_thread.start()
    return server_thread


def mock_server_acq(conn):
    """Make fake acq server.

    Parameters
    ----------
    conn : object
        Connector to the database

    Returns
    -------
    thread instance
        the instance of the server
    """
    host, port = node_info("dummy_acq")

    server_thread = threading.Thread(
        target=mock_acq_routine,
        args=(
            host,
            port,
            conn,
        ),
        daemon=True,
    )
    server_thread.start()
    return server_thread
