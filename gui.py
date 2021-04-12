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
            
            inlet = pylsl.StreamInlet(info, processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
            inlets[name] = inlet
    
        else:
            print('Don\'t know what to do with stream ' + info.name())


                    
def plot_ts(fig=None, axs=None):
    if fig is None:    
        fig, axs = plt.subplots(3,1, sharex=True)

    sampling = .1
    buff_size = 1024
      
    for nm, inlet in inlets.items():
        if nm in ['Marker', 'Markers']:
            continue
                    
        elif nm in ['Mouse', "mbient", "Audio"]:                    
            tv, ts = inlet.pull_chunk(timeout=0.0)

            if ts == []:
                continue                    
                
            clicks =[]
            if nm == "Mouse":
                ax_ith = 0
                clicks = [[tt,t[-1]] for t, tt in zip(tv, ts)if t[-1]!=0]
                tv = [t[:-1] for t in tv]
                
            elif nm == "mbient":
                ax_ith = 1
                tv = [[np.mean(t[:3]), np.mean(t[3:])] for t in tv]
                
            elif nm == "Audio":
                ax_ith = 2
                tv = [[np.mean(t) ]for t in tv]
                
            tv = np.array(tv)
            ts = np.array(ts)            
            sz = ts.shape[0] 
            
            if not hasattr( inlet, "line"):
                inlet.xdata = np.array(range(buff_size))
                inlet.ydata = np.zeros((buff_size, tv.shape[1]))
    
                inlet.line = axs[ax_ith].plot(inlet.xdata, inlet.ydata)
                         
            inlet.ydata = np.vstack((inlet.ydata[sz - buff_size:-1, :], tv))                
            inlet.xdata = np.hstack((inlet.xdata[sz - buff_size:-1], ts))
            
            for i, chn in enumerate(inlet.ydata.T):
                inlet.line[i].set_data(inlet.xdata, chn)
            
            if clicks != []:
                for clk in clicks:
                    clr = "g" if clk[1]==1 else "r" if clk[1]==-1 else "k"
                    axs[ax_ith].axvline(x=clk[0], color=clr)
                    
            axs[ax_ith].set_xlim([ max(ts) - (sampling*50) , max(ts)])
            ylim = inlet.ydata.flatten()
            axs[ax_ith].set_ylim([ min(ylim) , max(ylim)])
    
        inlets[nm] = inlet
        
    return fig, axs

            

def draw_figure(canvas, figure):
    figure_canvas_agg = FigureCanvasTkAgg(figure, canvas)
    figure_canvas_agg.draw()
    figure_canvas_agg.get_tk_widget().pack(side='top', fill='both', expand=1)
    return figure_canvas_agg


            
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
def plot_image(key_screen='-screen-', key_webcam='-webcam-'):   
    global inlets
    global plot_elem
    # print("In the thread")
    # if len(inlets) == 0:
        # print("len is 0 inlets")
    plot_elem = []
    for nm, inlet in inlets.items():

        tv, ts = inlet.pull_sample(timeout=0.0) 
        if ts == [] or ts is None:
             continue
                                      
        if nm == "Screen":    
            key = key_screen
            tv = tv[1:]  
            print("Screen")
        elif nm == "Webcam":
             key = key_webcam
             print("Webcam")
        else:
             continue
         
        frame = np.array(tv, dtype=np.uint8).reshape(frame_sz[1], frame_sz[0])
        imgbytes = cv2.imencode('.png', frame)[1].tobytes()
        
        plot_elem.append([key, imgbytes])
        # window[key].update(data=imgbytes)   
        # window.write_event_value("Thread", True)
   
thread_run = True
def img_loop():
    global thread_run
    print("In the thread loop" )
    while thread_run:
        plot_image( '-screen-', '-webcam-') 
    print("Closing image feed thread")
        
        
# def thread_img(prev_thread=None):
#     if prev_thread is not None:
#         print("Stopping thread")
#         prev_thread._stop()
    
#     print("starting thread")
#     img_thread = threading.Thread(target=img_loop, args=('-screen-', '-webcam-'))   
#     img_thread.start()
    
#     print(f"is alive: {img_thread.is_alive()}")
#     return img_thread
   
# img_thread = threading.Thread(target=img_loop)   
# img_thread.start()
    
# img_thread = thread_img()
plotting = False

fig, axs= None, None
fig_canvas_agg = None

def ts_plotting():
    global plotting, fig_canvas_agg
    global fig
    global axs
    global window
    print("plot func")
    plotting = True
    fig, axs = plot_ts(fig, axs)    
    if fig_canvas_agg is None:
        print("plot draw")
        fig_canvas_agg = draw_figure(window['-CANVAS-'].TKCanvas, fig)   
        plt.close()
    
    print("plot thread")
    threading.Thread(target=fig_canvas_agg.draw, daemon=True).start()
    plotting = False

session_saved = False

def ts_thread():
    global window
    global fig_canvas_agg
    global fig
    global axs
    print("plot thread")
    plot_ts(fig, axs)  
    print("plot thread1")
    
    window.write_event_value("Thread", True)
    

# def ts_thread():
#     global window
#     print("plot thread")   
#     print("plot thread1")
#     window.write_event_value("Thread", True)


        
fig, axs = plt.subplots(3,1, sharex=True)
while True:             # Event Loop
    event, values = window.read(0)
    if event == sg.WIN_CLOSED:
        break
    elif event == 'RTD':
        ctr_rec.prepare_feedback()
        print('RTD')
        update_streams()
        t = threading.Thread(target=img_loop)
        t.start()
        
    elif event == 'Devices':
        ctr_rec.prepare_devices()
        ctr_rec.initiate_labRec()
        print('Devices')
        update_streams()
        
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
        
        update_streams()
        ctr_rec.task_loop(tasks, session_info['subj_id']) 
        
        # session
    elif event == 'Stop':
        ctr_rec.close_all()
        session_saved = False
        print("Stopping devices")
        
    elif event ==  'Shut Down':
        ctr_rec.shut_all()   
        thread_run = False

    # if len(inlets) == 0:    
    #     update_streams()
           
    
    if plot_elem:
        print("Active image thread")
        for el in plot_elem:
            window[el[0]].update(data=el[1])  
          
    # else:
    #     print("starting image thread")
    #     threading.Thread(target=plot_image, daemon=True)
    # target=fig_canvas_agg.draw() 
    # if not plotting:
    #     ts_plotting()
    
    
        
window.close()
