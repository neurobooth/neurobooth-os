# Import socket module 
import socket 
import select
from time import time, sleep
# import wmi
import re
import os
from secrets_info import secrets


def socket_message(message, node_name, wait_data=0):
    
    def connect():        
        # t0 = time()
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
      
        # connect to server on local computer 
        s.connect((host,port)) 
        # print(f"* connected {time()- t0}")
        # t0 = time()
        s.send(message.encode('ascii'))    
        # print(f"sent {time()- t0}")    
        # t0 = time()
        data = None
        if wait_data:
           data = wait_socket_data(s)
       
        s.close()
        # print(f"closed {time()- t0}")   
        return data    
                  
    host, port = node_info(node_name)
    
    try:
        data = connect()
    except:# TimeoutError:
        print(f"{node_name} socket connexion timed out, trying to restart server")
        pid = start_server(node_name)
        # print(f"{pid} on server {node_name} created")
        data = connect()
    
    return data    


def socket_time(node_name, print_flag=1, time_out=3):
    
    host, port = node_info(node_name) 
              
    message = "time_test"    
    t0 = time()
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
    s.settimeout(time_out)
           
    try:
        # connect to server on local computer 
        s.connect((host,port)) 
    except:
        print(f"{node_name} socket connexion timed out, trying to restart server")
        start_server(node_name)
        t0 = time()
        s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
        s.settimeout(time_out*2)
        s.connect((host,port))
    
    s.send(message.encode('ascii'))        
    # messaga received from server 
    data = wait_socket_data(s, 2)    
    s.close()
    
    t1 = time()
    time_send = float( data.split("_")[-1])
    time_1way = time_send - t0
    time_2way = t1 - t0
    
    if print_flag:
        print(f"Return took {time_2way}, sent {time_1way}")       
    
    return  time_2way, time_1way
    

def node_info(node_name):    
    port = 12347
    if node_name == "acquisition":
        host = 'acq'  
    elif node_name == "presentation":
         host = 'stm'
    elif node_name == "control":        
         host = 'ctr' 
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
    """ Makes a network call to run python scripts serv_{node}.py
        :param node_name: node name pc to connect. 
        :type: str 
        :return: list of pids from created pythons
            
    """

    if node_name in [ "acquisition", "presentation"]:
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
     
    cmd_str = f"SCHTASKS /S {s['name']} /U {s['name']}\{s['user']} /P {s['pass']}"
    cmd_1 = cmd_str +  f" /Create /TN TaskOnEvent /TR {s['bat']} /SC ONEVENT /EC Application /MO *[System/EventID=777] /f"
    cmd_2 = cmd_str + ' /Run /TN "TaskOnEvent"'
    # out = os.popen(cmd_1).read()
    out = os.popen(cmd_2).read()
     
    sleep(.3)
    # tic = time()
    out = os.popen(task_cmd).read()
    pids_new = get_python_pids(out)
    # print(f"4 - {time() - tic}")
    
    pid =  [p for p in pids_new if p not in pids_old ]
    print(f"{node_name.upper()} server initiated with pid {pid}")
    
    if save_pid_txt:
        with open("server_pids.txt","a") as f:
            f.write( f"{pid}|{node_name}|{time()}\n")
    return pid


def get_python_pids(output_tasklist):
    # From popen tasklist output
    
    procs = output_tasklist.split("\n")
    re_pyth = re.compile("python.exe[\s]*([0-9]*)")
    
    pyth_pids = []
    for prc in procs:
        srch = re_pyth.search(prc)    
        if srch is not None:
            pyth_pids.append(srch.groups()[0])
    return pyth_pids


def kill_remote_pid(pids, node_name):
    
    if node_name in [ "acquisition", "presentation"]:
        s = secrets[node_name]
    else:
        print("Not a known node name")
        return None
    
    if isinstance(pids, str): pids = [pids]
    
    cmd = f"taskkill /S {s['name']} /U {s['user']} /P {s['pass']} /PID %s"
    for pid in pids:
        out = os.popen(cmd %pid)
        print(out.read())
    return


def kill_pid_txt(txt_name="server_pids.txt", node_name=None):
    
     if not os.path.exists(txt_name):
        return
    
     with open(txt_name,"r+") as f:
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
    
    