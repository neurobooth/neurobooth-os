# -*- coding: utf-8 -*-
"""
Created on Fri Apr  2 08:01:51 2021

@author: neurobooth
"""
from datetime import datetime
import os.path as op
import numpy as np

import PySimpleGUI as sg
import cv2

import neurobooth_os.iout.metadator as meta
import neurobooth_os.config as cfg


def _lay_butt(name, key=None):
    if key is None:
        key = name
    return sg.Button(name, button_color=("white", "black"), key=key)


def _space(n=10):
    return sg.Text(" " * n)


def _init_layout(conn, exclusion=None, frame_sz=(320, 240)):
    sg.theme("Dark Grey 9")
    sg.set_options(
        element_padding=(0, 0),
    )
    layout = [
        [
            sg.Text("First name:", pad=((0, 0), 0), justification="left"),
            sg.Input(
                key="first_name",
                size=(44, 1),
                background_color="white",
                text_color="black",
            ),
        ],
        [_space()],
        [
            sg.Text("Last name:", pad=((0, 0), 0), justification="left"),
            sg.Input(
                key="last_name",
                size=(44, 1),
                background_color="white",
                text_color="black",
            ),
        ],
        [_space()],
        [
            sg.Button(
                "Find subject",
                button_color="white",
                key="find_subject",
                enable_events=True,
            )
        ],
        [_space()],
        [sg.Listbox([], size=(30, 10), key="dob")],
        [_space()],
        [
            sg.Button(
                "Select subject",
                button_color="white",
                key="select_subject",
                size=(30, 1),
                enable_events=True,
            )
        ],
        [_space()],
        [
            sg.Text("Staff ID:", pad=((0, 0), 0), justification="left"),
            sg.Input(
                key="staff_id",
                size=(44, 1),
                background_color="white",
                text_color="black",
            ),
        ],
        [_space()],
        [
            sg.T("Study ID"),
            sg.Combo(
                meta.get_study_ids(conn),
                key="study_id",
                enable_events=True,
                size=(44, 1),
                readonly=True,
            ),
        ],
        [_space()],
        [
            sg.T("Collection ID"),
            sg.Combo(
                "", key="collection_id", enable_events=True, size=(44, 1), readonly=True
            ),
        ],
        [_space()],
        [
            sg.Text("Task combo: "),
            sg.Combo("", size=(64, 1), key="tasks", readonly=True),
        ],
        [_space()],
        [
            _space(),
            sg.ReadFormButton(
                "Save", button_color=("white", "black"), key="_init_sess_save_"
            ),
        ],
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

    # tasks = {"DSC_task_1": 'Symbol Digit Matching Task',
    #          "mouse_task_1": 'Mouse Task',
    #          'timing_test_1': 'Time testing',
    #          "pursuit_task_1": "Pursuit",
    #          "sit_to_stand_task_1": "Sit to stand"
    #          }

    tasks = {}  # Don't map as notes finelanme changes
    if tasks.get(task_name):
        name_present = tasks[task_name]
    else:
        name_present = task_name
    return name_present, task_name


def _make_tasks_checkbox(task_list):
    """makes task checkboxes in 3 columns.

    Task_list : str
        list of tasks,e.g. task1, task2,task3
    """

    tasks = task_list.split(", ")
    task_chunks = [tasks[i : i + 3] for i in range(0, (len(tasks)), 3)]

    field_tasks = []
    for chunk in task_chunks:
        task_col = []
        for task in chunk:
            name, key = task_mapping(task)
            # task_col.extend([_space(), sg.Checkbox(name, key=key, size=(44, 1), default=True)])
            task_col.extend([sg.Checkbox(name, key=key, size=(24, 1), default=True)])
        field_tasks.append([_space()] + task_col)
    return field_tasks


def _main_layout(sess_info, remote=False, frame_sz=(270, 480)):
    frame_cam = np.ones(frame_sz)
    imgbytes = cv2.imencode(".png", frame_cam)[1].tobytes()
    sg.theme("Dark Grey 9")
    sg.set_options(element_padding=(0, 0))

    field_tasks = _make_tasks_checkbox(sess_info["tasks"])

    if remote:
        console_output = [_space(3)]
    else:
        console_output = [
            sg.Text(
                "Console \n Output:",
                pad=((0, 0), 0),
                justification="left",
                auto_size_text=True,
            ),
            sg.Output(key="-OUTPUT-", size=(90, 28)),
        ]
    # console_output = [_space(3)]
    subject_text = (
        f'Subject ID: {sess_info["subject_id"]}, {sess_info["first_name"]}'
        + f' {sess_info["last_name"]}'
    )
    layout_col1 = (
        [
            [
                _space(),
                sg.Text(
                    subject_text,
                    pad=(20, 0),
                    size=(30, 1),
                    font=("Arial", 12, "bold"),
                    text_color="black",
                    background_color="white",
                    k="_sbj_id_",
                ),
                sg.Text(
                    f'Staff ID: {sess_info["staff_id"]}',
                    size=(20, 1),
                    font=("Arial", 12, "bold"),
                    text_color="black",
                    background_color="white",
                    k="_staff_id_",
                ),
            ],
            [_space()],
            [
                sg.Text(
                    "RC Notes:",
                    pad=((0, 0), 0),
                    justification="left",
                    k="_title_notes_",
                ),
                sg.Multiline(key="notes", default_text="", size=(64, 8)),
                _space(),
            ],
            [
                _space(),
                sg.Combo(
                    ["All tasks"]
                    + [task_mapping(t)[0] for t in sess_info["tasks"].split(", ")],
                    k="_notes_taskname_",
                ),
                sg.ReadFormButton("Save", key="_save_notes_"),
            ],
            [_space()],
        ]
        + field_tasks
        + [
            [_space()],
            [_space()],
            console_output,
            [_space()],
            [
                _space(1),
                _lay_butt("Initiate servers", "-init_servs-"),
                _space(5),
                _lay_butt("Connect Devices", "-Connect-"),
                _space(5),
                _lay_butt("Plot Devices", "plot"),
            ],
            [_space()],
            [
                _space(5),
                sg.ReadFormButton("Start", button_color=("white", "black")),
                _space(5),
                _lay_butt("Pause", "Pause tasks"),
                _space(5),
                _lay_butt("Terminate servers", "Shut Down"),
            ],
            [_space()],
        ]
    )

    layout_col2 = [
        [sg.Image(data=imgbytes, key="iphone", size=frame_sz)],
        [
            sg.Button(
                "IPhone preview",
                button_color=("white", "black"),
                key="-frame_preview-",
                visible=False,
            )
        ],
        [_space()],
        [_space()],
        [_space()],
        [sg.Text("", justification="left", k="task_title")],
        [sg.Text("", k="task_running", justification="left", size=(20, 1))],
        [_space()],
        [_space()],
        [_space()],
        [_space()],
        [sg.Text("Inlet streams")],
        [
            sg.Multiline(
                size=(40, 15), key="inlet_State", do_not_clear=False, no_scrollbar=True
            )
        ],
    ]

    layout = [
        [
            sg.Column(layout_col1, pad=(0, 0)),
            sg.Column(layout_col2, pad=(0, 0), element_justification="c"),
        ]
    ]
    return layout


def _win_gen(layout, *args):
    window = sg.Window(
        "Neurobooth",
        layout(*args),
        size=(1000, 1045),
        keep_on_top=False,
        resizable=True,
        location=(-7, 0),
        default_element_size=(10, 1),
        text_justification="l",
        auto_size_text=False,
        auto_size_buttons=False,
        #    no_titlebar=False,
        grab_anywhere=False,
        default_button_element_size=(12, 1),
    )
    return window


def write_task_notes(subject_id, staff_id, task_name, task_notes):
    """Write task notes.
    Parameters
    ----------
    subject_id : str
        The subject ID
    staff_id : str
        The RC ID
    task_name : str
        The task name.
    task_notes : str
        The task notes.
    """

    fname = f'{cfg.neurobooth_config["data_out"]}{subject_id}/{subject_id}-{task_name}-notes.txt'
    task_txt = ""
    if not op.exists(fname):
        task_txt += f"{subject_id}, {staff_id}\n"

    with open(fname, "a") as fp:
        datestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        task_txt += f"[\t{datestamp}]: {task_notes}\n"
        fp.write(task_txt)
