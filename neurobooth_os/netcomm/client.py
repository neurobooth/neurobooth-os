# Import socket module
import socket
import select
from time import time, sleep
import re
import os

from neurobooth_os.secrets_info import secrets


def socket_message(message, node_name, wait_data=False):
    """ Send a string message though socket connection to `node_name`.

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
        s.send(message.encode('ascii'))

        data = None
        if wait_data:
            data = wait_socket_data(s)

        s.close()
        return data

    host, port = node_info(node_name)

    try:
        data = connect()
    except TimeoutError:
        print(f"{node_name} socket connexion timed out, trying to restart server")
        pid = start_server(node_name)
        data = connect()

    return data


def socket_time(node_name, print_flag=1, time_out=3):
    """Computes connextion time from client->server and client->server->client.

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

    s.send(message.encode('ascii'))
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
    port = 12347
    if node_name == "acquisition":
        host = 'acq'
    elif node_name == "presentation":
        host = 'stm'
    elif node_name == "control":
        host = 'ctr'
    elif node_name == "dummy_acq":
        host = 'localhost'
        port = 80
    elif node_name == "dummy_stm":
        host = 'localhost'
        port = 81
    elif node_name == "dummy_ctr":
        host = 'localhost'
        port = 82
    return host, port


def wait_socket_data(s, wait_time=None):

    tic = time()
    while True:
        r, _, _ = select.select([s], [], [s], 1)
        if r:
            data = s.recv(1024)
            return data.decode("utf-8")

        if wait_time is not None:
            if time() - tic > wait_time:
                print("Socket timed out")
                return "TIMED-OUT_-999"


def start_server(node_name, save_pid_txt=True):
    """ Makes a network call to run script serv_{node_name}.bat

    First remote processes are logged, then a scheduled task is created to run
    the remote batch file, then task runs, and new python PIDs are captured with
    the option to save to save_pid_txt. If saved, when the function is called it
    will kill the PIDs in the file.

    Parameters
    ----------
    node_name : str
        PC node name defined in `secrets_info.secrets`
    save_pid_txt : bool
        Option to save PID to file for killing PID in the future.

    Returns
    -------
    pid : list
        Python process identifiers found in remote computer after server started.
    """

    if node_name in ["acquisition", "presentation"]:
        s = secrets[node_name]
    else:
        print("Not a known node name")
        return None
    # Kill any previous server
    kill_pid_txt(node_name=node_name)

    # tic = time()
    task_cmd = f"tasklist.exe /S {s['name']} /U {s['user']} /P {s['pass']}"
    out = os.popen(task_cmd).read()
    pids_old = get_python_pids(out)
    # print(f"2 - {time() - tic}")

    cmd_str = f"SCHTASKS /S {s['name']} /U {s['name']}\\{s['user']} /P {s['pass']}"
    cmd_1 = cmd_str + \
        f" /Create /TN TaskOnEvent /TR {s['bat']} /SC ONEVENT /EC Application /MO *[System/EventID=777] /f"
    cmd_2 = cmd_str + ' /Run /TN "TaskOnEvent"'
    # Cmd1 creates a scheduled task, cmd2 initiates it
    out = os.popen(cmd_1).read()
    out = os.popen(cmd_2).read()

    sleep(.3)
    # tic = time()
    out = os.popen(task_cmd).read()
    pids_new = get_python_pids(out)
    # print(f"4 - {time() - tic}")

    pid = [p for p in pids_new if p not in pids_old]
    print(f"{node_name.upper()} server initiated with pid {pid}")

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
        s = secrets[node_name]
    else:
        print("Not a known node name")
        return None

    if isinstance(pids, str):
        pids = [pids]

    cmd = f"taskkill /S {s['name']} /U {s['user']} /P {s['pass']} /PID %s"
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
