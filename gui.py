# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import PySimpleGUI as sg
import main_control_rec as ctr_rec
import pprint
import numpy as np
import cv2
import pylsl
import time
import threading

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import matplotlib



inlets = {}
frame_sz= (320, 240)

# Turn off padding in order to get a really tight looking layout.
def callback_RTD(values):    
    ctr_rec.prepare_feedback() # rint resp
    
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
    

def update_streams():
    streams = pylsl.resolve_streams() 
    inlets= {}
    for info in streams:            
        name = info.name()     
        inx=1
        # while True:
        #     if name in inlets.keys():
        #         name = name.split("_")[0] + f"_{inx}"
        #     else:  
        #         break
                
        if info.type() == 'Markers':
            print('(NOT YET) Adding marker inlet: ' + name)
            # inlets.append(MarkerInlet(info))
            
        elif info.name()  in ["Screen", "Webcam", "Mouse", "Audio", "mbient"]:
            print('Adding data inlet: ' + name)
            
            inlet = pylsl.StreamInlet(info, recover=False)
            inlets[name] = inlet
    
        else:
            print('Don\'t know what to do with stream ' + info.name())
    return inlets

     
            
def lay_butt(name, key=None):
    if key is None:
        key = name
    return sg.Button(name, button_color=('white', 'black'), key=key)

def space(n=10):
    return sg.Text(' ' * n)

    
frame_cam = np.ones(frame_sz)
imgbytes = cv2.imencode('.png', frame_cam)[1].tobytes() 
    
   
sg.theme('Dark Grey 9')
sg.set_options(element_padding=(0, 0))
layout_col1 = [[sg.Text('Subject ID:', pad=((0, 0), 0), justification='left'), sg.Input(key='subj_id', size=(44, 1), background_color='white', text_color='black')],
          [space()],
          [sg.Text('RC ID:', pad=((0, 0), 0), justification='left'), sg.Input(key='rc_id', size=(44, 1), background_color='white', text_color='black')],
          [space()],
          [sg.Text('RC Notes:', pad=((0, 0), 0), justification='left'),  sg.Multiline(key='notes', default_text='', size=(54, 15)), space(), sg.Canvas(key='-CANVAS-')],
          [space()],          
          [space()],
          [space(), sg.Checkbox('Symbol Digit Matching Task', key='fakest_task', size=(44, 1))],
          [space(), sg.Checkbox('Mouse Task', key='extra_fakest_task', size=(44, 1))],
          [space()],          
          [space(), sg.ReadFormButton('Save', button_color=('white', 'black'))],         
          [space()],
          [space()],
          [sg.Text('Console Output:', pad=((0, 0), 0), justification='left'), sg.Output(key='-OUTPUT-', size=(54, 15))],
          [space()],
          # [space()],
          [space(1), lay_butt('Test Comm', 'Test_network'),space(5), lay_butt('Display', 'RTD'), 
           space(5), lay_butt('Prepare Devices', 'Devices'), space(5)],
          [space()],
          [space(5), sg.ReadFormButton('Start', button_color=('white', 'black')), space(5), lay_butt('Stop'),
           space(), sg.ReadFormButton('Shut Down', button_color=('white', 'black'))],
          ]


layout_col2 = [#[space()], [space()], [space()], [space()],
               [sg.Image(data=imgbytes, key='-screen-', size=frame_sz)], 
                [space()], [space()], [space()], [space()],
               [sg.Image(data=imgbytes, key='-webcam-', size=frame_sz)]
               ]

# layout = [[sg.Column(left_col, element_justification='c'), sg.VSeperator(),sg.Column(images_col, element_justification='c')]]

layout = [[sg.Column(layout_col1,  pad=(0,0)), sg.Column(layout_col2, pad=(0,0))] ]

window = sg.Window("Neurobooth",
                   layout,
                   default_element_size=(10, 1),
                   text_justification='l',
                   auto_size_text=False,
                   auto_size_buttons=False,
                   no_titlebar=False,
                   grab_anywhere=True,
                   default_button_element_size=(12, 1))


inlets = {}
plot_elem = []
def plot_image2(inlets, window, key_screen='-screen-', key_webcam='-webcam-'):   

    plot_elem = []
    for nm, inlet in inlets.items():        
        tv, ts = inlet.pull_sample(timeout=0.0)
        if ts == [] or ts is None:
             continue
                                      
        if nm == "Screen":    
            key = key_screen
            tv = tv[1:]  
           
        elif nm == "Webcam":
            key = key_webcam
            
        else:
             continue
         
        frame = np.array(tv, dtype=np.uint8).reshape(frame_sz[1], frame_sz[0])
        imgbytes = cv2.imencode('.png', frame)[1].tobytes()
        
        plot_elem.append([key, imgbytes])
        # window[key].update(data=imgbytes)   
        # window.write_event_value("Thread", True)
    return  plot_elem
        
thread_run = True
def img_loop():
    global thread_run
    print("In the thread loop" )
    while thread_run:
        plot_image2( '-screen-', '-webcam-') 
    print("Closing image feed thread")
        
        


while True:             # Event Loop
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
        session_info = values        
        tasks = get_tasks(values)
        session_saved = True
        print(values)
        
    elif event == 'Test_network':
        ctr_rec.test_lan_delay(50)
        
    elif event == 'Start':
        if not session_saved:
            session_info, tasks =  get_session_info(values)
            print(values)
        
        inlets = update_streams()
        ctr_rec.task_loop(tasks, session_info['subj_id']) 
        
        # session
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
        plot_elem =  plot_image2(inlets, window) 
        for el in plot_elem:
            window[el[0]].update(data=el[1])

        
        
window.close()
