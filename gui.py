# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import PySimpleGUI as sg
import numpy as np
import cv2
import pylsl
import time
import threading
import matplotlib
import queue
import main_control_rec as ctr_rec
from realtime.lsl_plotter import update_streams, get_lsl_images
from netcomm.server_ctr import server_com

# from netcomm.server_ctr import test as server_com
    
def get_session_info(values):
     session_info = values        
     tasks = get_tasks(values)
     return session_info, tasks
    
    
def get_tasks(values): 
    tasks= []
    for key, val in values.items():
        if "task" in key and val is True:
            tasks.append(key)
    return tasks            


serv_event = queue.Queue(maxsize=10)
def feedback_com():
    global serv_event    
    def callback(inp):
        serv_event.put(inp)
               
    server_com(callback)


thr = threading.Thread(target=feedback_com, daemon=True)
thr.start()
        
def lay_butt(name, key=None):
    if key is None:
        key = name
    return sg.Button(name, button_color=('white', 'black'), key=key)


def space(n=10):
    return sg.Text(' ' * n)


frame_sz= (320, 240)    
frame_cam = np.ones(frame_sz)
imgbytes = cv2.imencode('.png', frame_cam)[1].tobytes()
    
sg.theme('Dark Grey 9')
sg.set_options(element_padding=(0, 0))
layout_col1 = [
    [sg.Text('Subject ID:', pad=((0, 0), 0), justification='left'), sg.Input(key='subj_id', size=(44, 1), background_color='white', text_color='black')],
    [space()],
    [sg.Text('RC ID:', pad=((0, 0), 0), justification='left'),  sg.Input(key='rc_id', size=(44, 1), background_color='white', text_color='black')],
    [space()],
    [sg.Text('RC Notes:', pad=((0, 0), 0), justification='left'),  sg.Multiline(key='notes', default_text='', size=(64, 10)), space()],
    [space()],          
    [space()],
    [space(), sg.Checkbox('Symbol Digit Matching Task', key='DSC_task', size=(44, 1))],
    [space(), sg.Checkbox('Mouse Task', key='mouse_task', size=(44, 1))],
    [space()],          
    [space(), sg.ReadFormButton('Save', button_color=('white', 'black'))],         
    [space()],
    [space()],
    [sg.Text('Console \n Output:', pad=((0, 0), 0), justification='left', auto_size_text=True), sg.Output(key='-OUTPUT-', size=(84, 30))],
    [space()],
    # [space()],
    [space(1), lay_butt('Test Comm', 'Test_network'),space(5), lay_butt('Display', 'RTD'), 
     space(5), lay_butt('Prepare Devices', 'Devices'), space(5)],
    [space()],
    [space(5), sg.ReadFormButton('Start', button_color=('white', 'black')), space(5), lay_butt('Stop'),
     space(), sg.ReadFormButton('Shut Down', button_color=('white', 'black'))],
    ]

layout_col2 = [#[space()], [space()], [space()], [space()],
               [sg.Image(data=imgbytes, key='Screen', size=frame_sz)], 
                [space()], [space()], [space()], [space()],
               [sg.Image(data=imgbytes, key='Webcam', size=frame_sz)]
               ]

layout = [[sg.Column(layout_col1,  pad=(0,0)), sg.Column(layout_col2, pad=(0,0), element_justification='c')] ]

window = sg.Window("Neurobooth",
                   layout,
                   default_element_size=(10, 1),
                   text_justification='l',
                   auto_size_text=False,
                   auto_size_buttons=False,
                   no_titlebar=False,
                   grab_anywhere=False,
                   default_button_element_size=(12, 1))
        

        
inlets = {}
plot_elem = []
running_task, start_tasks = None, False
done_tasks = []
while True:
    event, values = window.read(1)
    if event == sg.WIN_CLOSED:
        break
    
    elif event == 'RTD':
        ctr_rec.prepare_feedback()
        print('RTD')
        time.sleep(.5)
        inlets = update_streams()
        
    elif event == 'Devices':
        ctr_rec.prepare_devices()
        ctr_rec.initiate_labRec()
        print('Devices')
        inlets = update_streams()
        
    elif event == 'Save':
        session_info, tasks = get_session_info(values)
        session_saved = True
        print(values)
        
    elif event == 'Test_network':
        _ = ctr_rec.test_lan_delay(100)
        
    elif event == 'Start':
        if not session_saved:
            session_info, tasks = get_session_info(values)
            print(values)
        
        inlets = update_streams()
        time.sleep(.5)
        
        if len(tasks):
            start_tasks= True
            running_task = tasks.pop(0)
            ctr_rec.task_presentation(running_task, session_info['subj_id'])
        else:
            print("Start button pressed but no task selected")      
        
    elif event == 'Stop':
        for k in inlets.keys():
            if k not in ["Webcam", "Screen"]:
                inlets[k].close_stream()                
        ctr_rec.close_all()
        session_saved = False
        print("Stopping devices")
        
    elif event ==  'Shut Down':
        for k in inlets.keys():
            if k in ["Webcam", "Screen"]:
                inlets[k].close_stream()
        ctr_rec.shut_all()    
        inlets = {}

    if len(inlets):
        plot_elem = get_lsl_images(inlets) 
        for el in plot_elem:
            window[el[0]].update(data=el[1])
           
        
    try:
        event_feedb = serv_event.get(False)
        print(f"Got this msg: {event_feedb}")
        
    except queue.Empty:
       # event_feedb = []
       pass
    

        
        
window.close()
