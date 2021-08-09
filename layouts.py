# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import PySimpleGUI as sg
import numpy as np
import cv2

        
def lay_butt(name, key=None):
    if key is None:
        key = name
    return sg.Button(name, button_color=('white', 'black'), key=key)


def space(n=10):
    return sg.Text(' ' * n)
 
def init_layout(exclusion=None, frame_sz=(320, 240)):
   
        
    sg.theme('Dark Grey 9')
    sg.set_options(element_padding=(0, 0))
    layout = [
        [sg.Text('Subject ID:', pad=((0, 0), 0), justification='left'), sg.Input(default_text="test", key='subj_id', size=(44, 1), background_color='white', text_color='black')],
        [space()],
        [sg.Text('RC ID:', pad=((0, 0), 0), justification='left'),  sg.Input(default_text="AN", key='rc_id', size=(44, 1), background_color='white', text_color='black')],
        [space()],
        [sg.T("Study ID"), sg.Input(default_text="Neurobooth", key='study_id', size=(44, 1))],
        [space()],     
        [sg.Text('Task combo: '), sg.Combo(['Timing test', "Pursuit, DSC, Mouse, Sit to stand"],  size=(44, 1), key="_tasks_")],
        # [lay_butt("Exclude tasks", key="_exclusion_")],
        [space()],     
        [space(), sg.ReadFormButton('Save', button_color=('white', 'black'), key="_init_sess_save_")],              
        ]
    
    return layout

def task_mapping(task_name):
    tasks = {"DSC":('Symbol Digit Matching Task', 'DSC_task'),
             "Mouse": ('Mouse Task', 'mouse_task'),
             'Timing test' : ('Time testing', 'timing_task'),
             "Pursuit" : ("Pursuit", "pursuit_task"),
             "Sit to stand" : ("Sit to stand", "sit_to_stand_task")
             
             }
    return tasks[task_name]
    

def main_layout(sess_info, frame_sz=(320, 240)):
    frame_cam = np.ones(frame_sz)
    imgbytes = cv2.imencode('.png', frame_cam)[1].tobytes()
    sess_info, = sess_info
    sg.theme('Dark Grey 9')
    sg.set_options(element_padding=(0, 0))
    
    field_tasks = []
    for task in sess_info['_tasks_'].split(", "):
        name, key = task_mapping(task)
        field_tasks.append([space(), sg.Checkbox(name, key=key, size=(44, 1), default=True)])
        
    layout_col1 = [
        [sg.Text(f'Subject ID: {sess_info["subj_id"]}', pad=((0, 0), 0), justification='left',  size=(44, 1))],
        [space()],
        [sg.Text(f'RC ID: {sess_info["rc_id"]}', pad=((0, 0), 0), justification='left')],
        [space()],
        [sg.Text('RC Notes:', pad=((0, 0), 0), justification='left'),  sg.Multiline(key='notes', default_text='', size=(64, 10)), space()],
        [space(), sg.Combo([task_mapping(t)[0] for t in sess_info['_tasks_'].split(", ")]),
         sg.ReadFormButton('Save', key="_task_notes_")],  
        [space()]
        ] + field_tasks + [       
        [space()],  
        [space()],
        [sg.Text('Console \n Output:', pad=((0, 0), 0), justification='left', auto_size_text=True), sg.Output(key='-OUTPUT-', size=(84, 30))],
        [space()],
        # [space()],
        [space(1), lay_butt('Initiate servers', 'init_servs'),         
         space(5), lay_butt('Display', 'RTD'), 
         space(5), lay_butt('Connect Devices', 'Connect'),
         space(5), lay_butt('Plot Devices', 'plot'),
         space(5), lay_butt('Connect Eyelink', 'eyetracker'),
          ],
        [space()],
        [space(5), lay_butt('Terminate servers','Shut Down'),
         space(5), sg.ReadFormButton('Start', button_color=('white', 'black')),
         space(5), lay_butt('Stop'),
         space(5), lay_butt('Test Comm', 'Test_network')         
        ]]
    
    layout_col2 = [[sg.Image(data=imgbytes, key='Screen', size=frame_sz)], 
                   [space()], [space()], [space()], [space()],
                   [sg.Image(data=imgbytes, key='Webcam', size=frame_sz)],
                   [space()], [space()], [space()], [space()],
                   [space()], [space()], [space()], [space()],
                   [sg.Text('Inlet streams')],
                   [sg.Multiline( size=(35, 6),  key='inlet_State', do_not_clear=False, no_scrollbar=True)]
                   ]
    
    layout = [[sg.Column(layout_col1,  pad=(0,0)), sg.Column(layout_col2, pad=(0,0), element_justification='c')] ]
    return layout

def win_gen(layout, *args):
    window = sg.Window("Neurobooth",
                       layout(args), 
                       # keep_on_top=True,
                       location =(0,0),
                       default_element_size=(10, 1),
                       text_justification='l',
                       auto_size_text=False,
                       auto_size_buttons=False,
                       no_titlebar=False,
                       grab_anywhere=False,
                       default_button_element_size=(12, 1))
    return window

# window = win_gen(init_layout)


# inlet_keys = []
# while True:
#     event, values = window.read()
#     print(event, values)
#     if event == sg.WIN_CLOSED:
#         break
#     if event == "_init_sess_save_":
#         if values["_tasks_"] == "":
#             sg.PopupError('No task combo')
#         else:
#             sess_info = values
#             window.close()
#             window = win_gen(main_layout, sess_info)
# window.close()