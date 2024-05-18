# Import socket module
import logging
import socket
import select
from time import time, sleep
import re
import os
import pandas as pd
from io import StringIO

import neurobooth_os.config as cfg

def setup_log(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger


logger = setup_log(__name__)


def socket_message(message, node_name, wait_data=False):
    """Send a string message though socket connection to `node_name`.

    Parameters
    ----------
    message : str
        The message to send.
    node_name : str
        The node to send the socket message to
    wait_data : bool
        If True, wait for the data.

    Returns
    -------
    data : str
        Returns the data from the node_name.
    """

    def connect():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        # connect to server on local computer
        s.connect((host, port))
        s.send(message.encode("ascii"))
        logger.info("Connecting to host: {host} and port: {port}")

        data = None
        if wait_data:
            data = wait_socket_data(s)

        s.close()
        return data

    host, port = node_info(node_name)

    try:
        data = connect()
    except (TimeoutError, ConnectionRefusedError) as e:
        logger.error(f"Unable to connect to client: {e}. Retrying.")
        try:
            data = connect()
        except Exception as e:
            logger.error(f"Unable to connect client after retry: {e}.")
            return
    except Exception as e:
        logger.error(f"An unexpected exception occurred while connecting to client: {e}.")
        return
    return data


def socket_time(node_name, print_flag=1, time_out=3):
    """Computes connection time from client->server and client->server->client.

    Parameters
    ----------
    node_name : str
        name of the server
    print_flag : int, optional
        if True, prints time taken
    time_out : int, optional
        Time of seconds waiting to hear from server, by default 3

    Returns
    -------
    times floats
        taken time to server and time to server and back
    """

    host, port = node_info(node_name)

    message = "time_test"
    t0 = time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(time_out)

    try:
        # connect to server on local computer
        s.connect((host, port))
    except BaseException:
        print(f"{node_name} socket connexion timed out, trying to restart server")
        start_server(node_name)
        t0 = time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(time_out * 2)
        s.connect((host, port))

    s.send(message.encode("ascii"))
    # message received from server
    data = wait_socket_data(s, 2)
    s.close()

    t1 = time()
    time_send = float(data.split("_")[-1])
    time_1way = time_send - t0
    time_2way = t1 - t0

    if print_flag:
        print(f"Return took {time_2way}, sent {time_1way}")

    return time_2way, time_1way


def node_info(node_name):
    """Gets the host and port of the node_name.

    Parameters
    ----------
    node_name : str
        Name of the node from which port and host is retrieved.

    Returns
    -------
    host str
        name of the host
    port int
        port number
    """
    server = cfg.neurobooth_config.server_by_name(node_name)
    host = server.name
    port = server.port
    logger.debug(f"Host is {host}, and port is {port}.")
    return host, port


def _socket_receive_data(sock, pack_len):
    # Helper function to recv n bytes or return None if EOF is hit
    fragments = []
    MAX_RECV = 130992
    buff_recv = 0
    while True:
        bytes_to_pull = pack_len
        if (pack_len - buff_recv) < MAX_RECV:
            bytes_to_pull = pack_len - buff_recv
        packet = sock.recv(bytes_to_pull)
        buff_recv += len(packet)
        fragments.append(packet)
        if buff_recv >= pack_len:
            break
    data = b"".join(fragments)
    return data


def wait_socket_data(s, wait_time=None):

    tic = time()
    while True:
        r, _, _ = select.select([s], [], [s], 1)
        if r:
            data = s.recv(1024)
            if data.startswith(b"::BYTES::"):
                split_data = data.split(b"::")
                split_data_len = int(split_data[2].decode("utf-8"))
                current_data = split_data[3]
                remainder_len = split_data_len - len(current_data)
                remainder_data = _socket_receive_data(s, remainder_len)
                data = current_data + remainder_data

            else:
                data = data.decode("utf-8")
            return data

        if wait_time is not None:
            if time() - tic > wait_time:
                print("Socket timed out")
                return "TIMED-OUT_-999"


def start_server(node_name, save_pid_txt=True):
    """Makes a network call to run script serv_{node_name}.bat

    First remote processes are logged, then a scheduled task is created to run
    the remote batch file, then task runs, and new python PIDs are captured with
    the option to save to save_pid_txt. If saved, when the function is called it
    will kill the PIDs in the file.

    Parameters
    ----------
    node_name : str
        PC node name defined in config.neurobooth_config`
    save_pid_txt : bool
        Option to save PID to file for killing PID in the future.

    Returns
    -------
    pid : list
        Python process identifiers found in remote computer after server started.
    """

    if node_name in ["acquisition", "presentation"]:
        s = cfg.neurobooth_config.server_by_name(node_name)
    else:
        print("Not a known node name")
        return None
    # Kill any previous server
    kill_pid_txt(node_name=node_name)

    logger.debug(f"Attempting to start server: {node_name}")
    logger.debug(f"Server {node_name} has configuration: {s} ")

    # get list of python processes
    task_cmd = f"tasklist.exe /S {s.name} /U {s.user} /P {s.password}"
    out = os.popen(task_cmd).read()
    logger.debug(f"Python processes found: {out}")
    pids_old = get_python_pids(out)

    # Get list of scheduled tasks and run TaskOnEvent if not running
    cmd_out = f"SCHTASKS /query /fo CSV /nh /S {s.name} /U {s.name}\\{s.user} /P {s.password}"
    out = os.popen(cmd_out).read().replace("\\", "")
    df = pd.read_csv(StringIO(out), sep=",", index_col=0, names=["date", "status"])

    task_name = "TaskOnEvent1"
    while True:
        if task_name in out:
            # if task already running add n+1 to task name
            if df.loc[task_name, "status"] == "Running":
                tsk_inx = int(task_name[-1]) + 1
                task_name = task_name[:-1] + str(tsk_inx)
                print(f"Creating new scheduled task: {task_name} in server {node_name}")
                continue
        break

    # Run scheduled task cmd1 creates a scheduled task, cmd2 initiates it
    cmd_str = f"SCHTASKS /S {s.name} /U {s.name}\\{s.user} /P {s.password}"
    cmd_1 = (
        cmd_str
        + f" /Create /TN {task_name} /TR {s.bat} /SC ONEVENT /EC Application /MO *[System/EventID=777] /f"
    )
    out = os.popen(cmd_1).read()

    cmd_2 = cmd_str + f" /Run /TN {task_name}"
    out = os.popen(cmd_2).read()

    sleep(0.3)
    out = os.popen(task_cmd).read()

    pids_new = get_python_pids(out)

    pid = [p for p in pids_new if p not in pids_old]
    print(f"{node_name.upper()} server initiated with pid {pid}")
    logger.info(f"{node_name.upper()} server initiated with pid {pid}")

    if save_pid_txt:
        with open("server_pids.txt", "a") as f:
            f.write(f"{pid}|{node_name}|{time()}\n")
    return pid


def get_python_pids(output_tasklist):
    # From popen tasklist output

    procs = output_tasklist.split("\n")
    re_pyth = re.compile("python.exe[\\s]*([0-9]*)")

    pyth_pids = []
    for prc in procs:
        srch = re_pyth.search(prc)
        if srch is not None:
            pyth_pids.append(srch.groups()[0])
    return pyth_pids


def kill_remote_pid(pids, node_name):

    if node_name in ["acquisition", "presentation"]:
        s = cfg.neurobooth_config.server_by_name(node_name)
    else:
        print("Not a known node name")
        return None

    if isinstance(pids, str):
        pids = [pids]

    cmd = f"taskkill /S {s.name} /U {s.user} /P {s.password} /PID %s"
    for pid in pids:
        out = os.popen(cmd % pid)
        print(out.read())
    return


def kill_pid_txt(txt_name="server_pids.txt", node_name=None):

    if not os.path.exists(txt_name):
        return

    with open(txt_name, "r+") as f:
        Lines = f.readlines()

        if len(Lines):
            print(f"Closing {len(Lines)} remote processes")

        new_lines = []
        for line in Lines:
            pid, node, tsmp = line.split("|")
            if node_name is not None and node_name != node:
                new_lines.append(line)
                continue
            kill_remote_pid(eval(pid), node)

        f.seek(0)
        if len(new_lines):
            f.writelines(new_lines)
        else:
            f.write("")
        f.truncate()
