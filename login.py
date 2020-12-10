import eel
import sqlite3 as sql
import json
import os
import socket
import time
from pylsl import StreamInfo, StreamOutlet, resolve_byprop, StreamInlet
from time import time
from io.marker import marker_stream


outlet_marker = marker_stream()

info = StreamInfo('Markers', 'Markers', 1, 0, 'int32', 'myuidw43536')
outlet_trigger = StreamOutlet(info)


eel.init('www', ['.js', '.html', '.jpg'])
con = sql.connect('users.db')
c = con.cursor()
subject = ''


def create_db():
    
    c.execute(''' CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        password TEXT
    )''')

@eel.expose
def register(username,password):
    
    c.execute("SELECT * FROM users WHERE username=:user",{"user":username})
    check = c.fetchall()
    
    if len(check) == 0:
        c.execute("INSERT INTO users(username,password) VALUES (:username,:password)",{"username":username,"password":password})
        con.commit()

        return 1
    else:
        return 0

@eel.expose
def login(username,password):
    c.execute("SELECT * FROM users WHERE username=:user",{"user":username})
    check = c.fetchall()

    
    if len(check) == 1 and check[0][2] == password:
        return 1
    else:
        return 0

@eel.expose
def get_data_mt(sub_id, file_name, data):
    print(sub_id)
    subject = sub_id
    with open(os.path.join('data', file_name + '.json'), 'w', encoding='utf-8') as f:
        json.dump(data[1:-1], f, ensure_ascii=False, indent=4)

@eel.expose
def get_data_dsst(results, score, outcomes):
    print(results, score, outcomes)

@eel.expose
def js_trigger(message): 
    message = message +  "_" + str(time())
    # local host IP '127.0.0.1' 
    host = '172.19.128.22'
    port = 12347
    s = socket.socket(socket.AF_INET,socket.SOCK_STREAM) 
    s.connect((host,port)) 
    print(message)
    timestamp = time()
    outlet_trigger.push_sample([1], timestamp)
    # Define the port on which you want to connect 
 
    # message you send to server 
    s.send(message.encode('ascii')) 
    #data = s.recv(1024)

    #print('Received from the server :',str(data.decode('ascii'))) 

    s.close() 
    
@eel.expose
def get_inlet(name): 
    marker_streams = resolve_byprop('name', name)
    if marker_streams:
        inlet_marker = StreamInlet(marker_streams[0])
    else:
        inlet_marker = False
        print("Can't find Markers stream.")
    return inlet_marker
 
     
@eel.expose
def send_marker(message, number=""):
     outlet_marker.push_sample([f"{message}_{number}_{time.time()}"])      

    
create_db()  
# eel.start('register.html', size= (3840, 2160), cmdline_args=['--start-fullscreen', '--kisok'], geometry={'size': (3840, 2160), 'position': (0, 0)})
eel.start('synch_task.html', size= (3840, 2160), cmdline_args=['--start-fullscreen', '--kisok'], geometry={'size': (3840, 2160), 'position': (0, 0)})


print(subject)


   