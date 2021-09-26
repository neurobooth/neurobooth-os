# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""

import PySimpleGUI as sg

import cv2
import numpy as np

import neurobooth_os.iout.metadator as meta


def _lay_butt(name, key=None):
    if key is None:
        key = name
    return sg.Button(name, button_color=('white', 'black'), key=key)


def _space(n=10):
    return sg.Text(' ' * n)


def _init_layout(conn, exclusion=None, frame_sz=(320, 240)):
    sg.theme('Dark Grey 9')
    sg.set_options(element_padding=(0, 0),)
    layout = [
        [sg.Text('Subject ID:', pad=((0, 0), 0), justification='left'), sg.Combo(meta.get_subj_ids(conn), default_value="test", key='subj_id', size=(44, 1), background_color='white', text_color='black')],
        [_space()],
        [sg.Text('Staff ID:', pad=((0, 0), 0), justification='left'),  sg.Input(default_text="AN", key='staff_id', size=(44, 1), background_color='white', text_color='black')],
        [_space()],
        [sg.T("Study ID"),  sg.Combo(meta.get_study_ids(conn), key='study_id', enable_events=True, size=(44, 1))],
        [_space()],  
        [sg.T("Collection ID"),  sg.Combo("", key='collection_id', enable_events=True, size=(44, 1))],
        [_space()],   
        [sg.Text('Task combo: '), sg.Combo("",  size=(64, 1), key="_tasks_")],
        [_space()],     
        [_space(), sg.ReadFormButton('Save', button_color=('white', 'black'), key="_init_sess_save_")],              
        ]
    
    return layout


def task_mapping(task_name):
    """Map a stimulus name to a readable string

    Parameters
    ----------
    task_name : str
        Name of the task from the database, eg name_task_1

    Returns
    -------
    presentable task name : str
        readable task name
    input : str
        task_name
    """

    tasks = {"DSC_task_1": 'Symbol Digit Matching Task',
             "mouse_task_1": 'Mouse Task',
             'timing_test_1': 'Time testing',
             "pursuit_task_1": "Pursuit",
             "sit_to_stand_task_1": "Sit to stand"
             }

    if tasks.get(task_name):
        name_present = tasks[task_name]
    else:
        name_present = task_name
    return name_present, task_name


def _main_layout(sess_info, frame_sz=(320, 240)):
    frame_cam = np.ones(frame_sz)
    imgbytes = cv2.imencode('.png', frame_cam)[1].tobytes()
    sg.theme('Dark Grey 9')
    sg.set_options(element_padding=(0, 0))

    field_tasks = []
    for task in sess_info['_tasks_'].split(", "):
        name, key = task_mapping(task)
        field_tasks.append([_space(), sg.Checkbox(name, key=key, size=(44, 1), default=True)])

    layout_col1 = [
        [_space(), sg.Text(f'Subject ID: {sess_info["subj_id"]}', pad =(20, 0 ), size=(20, 1), 
         font=("Arial", 12, "bold"), text_color="black", background_color="white", k="_sbj_id_"),
         sg.Text(f'Staff ID: {sess_info["staff_id"]}',  size=(20, 1), font=("Arial", 12, "bold"),
          text_color="black", background_color="white", k="_staff_id_")
         ],
        [_space()],

        [sg.Text('RC Notes:', pad=((0, 0), 0), justification='left', k="_title_notes_"),
         sg.Multiline(key='notes', default_text='', size=(64, 10)), _space()],
        [_space(), sg.Combo([task_mapping(t)[0] for t in sess_info['_tasks_'].split(", ")],
         k="_notes_task_"), sg.ReadFormButton('Save', key="_save_notes_")],
        [_space()]

        ] + field_tasks + [
        [_space()],
        [_space()],

        # [sg.Text('Console \n Output:', pad=((0, 0), 0), justification='left',
        #          auto_size_text=True), sg.Output(key='-OUTPUT-', size=(84, 30))],
        [_space()],

        [_space(1), _lay_butt('Initiate servers', 'init_servs'),         
         _space(5), _lay_butt('Display', 'RTD'), 
         _space(5), _lay_butt('Connect Devices', 'Connect'),
         _space(5), _lay_butt('Plot Devices', 'plot'),
         ],         
        [_space()],

        [_space(5), _lay_butt('Terminate servers', 'Shut Down'),
         _space(5), sg.ReadFormButton('Start', button_color=('white', 'black')),
         _space(5), _lay_butt('Test Comm', 'Test_network')
         ]]

    layout_col2 = [[sg.Image(data=imgbytes, key='Webcam', size=frame_sz)],
                   [_space()], [_space()], [_space()], [_space()],
                   [sg.Text('', justification='left', k="task_title")],
                   [sg.Text('', k="task_running", justification='left', size=(20, 1))],
                   [_space()], [_space()], [_space()], [_space()],
                   [sg.Text('Inlet streams')],
                   [sg.Multiline(size=(35, 10), key='inlet_State', do_not_clear=False, no_scrollbar=True)]
                   ]

    layout = [[sg.Column(layout_col1, pad=(0, 0)), sg.Column(
        layout_col2, pad=(0, 0), element_justification='c')]]
    return layout


def _win_gen(layout, *args):
    window = sg.Window("Neurobooth",
                       layout(*args), 
                       # keep_on_top=True,
                       location=(0, 0),
                       default_element_size=(10, 1),
                       text_justification='l',
                       auto_size_text=False,
                       auto_size_buttons=False,
                       no_titlebar=False,
                       grab_anywhere=False,
                       default_button_element_size=(12, 1))
    return window

