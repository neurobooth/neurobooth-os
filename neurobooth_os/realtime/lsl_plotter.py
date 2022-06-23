# -*- coding: utf-8 -*-
"""
Created on Fri Mar 19 17:43:09 2021

@author: Adonay
"""

import numpy as np
import pylsl
import matplotlib.pyplot as plt
import matplotlib
import cv2
import threading
import time


def create_lsl_inlets(stream_ids):
    """Create LSL inlets on CTR computer.

    Parameters
    ----------
    stream_ids : dict of str
        The source IDs received from ACQ computer.

    Returns
    -------
    dict of StreamInlet
        The inlet streams.
    """
    inlets = {}
    for id_stream in stream_ids.values():
        stream = pylsl.resolve_byprop("source_id", id_stream, timeout=1)
        if stream:
            inlet = pylsl.StreamInlet(stream[0])
            inlets[stream[0].name()] = inlet
    return inlets


def get_lsl_images(inlets, frame_sz=(320, 240)):
    plot_elem = []
    for nm, inlet in inlets.items():
        tv, ts = inlet.pull_sample(timeout=0.0)
        if ts == [] or ts is None:
            continue

        if nm not in [ "Webcam"]:
            continue

        if nm == "Screen":
            tv = tv[1:]

        frame = np.array(tv, dtype=np.uint8).reshape(frame_sz[1], frame_sz[0])
        imgbytes = cv2.imencode('.png', frame)[1].tobytes()
        plot_elem.append([nm, imgbytes])
        inlet.flush()

    return plot_elem


class stream_plotter():
    def __init__(self):
        self.inlets = {}
        self.pltotting_ts = False

    def start(self, inlets):
        if  self.pltotting_ts:
            self.stop()

        self.pltotting_ts = True
        self.inlets = inlets

        if any([True for k in ['Mouse', "mbient", "Audio", "EyeLink"] if any(k in v for v in list(inlets))]):       
            print("starting thread update_ts")
            self.thread_ts = threading.Thread(target=self.update_ts, daemon=True)
            self.thread_ts.start()
        else:
            self.pltotting_ts = False

    def stop(self):
        if self.pltotting_ts:
            self.pltotting_ts = False
            self.thread_ts.join()
            print("Closed plotting windows")
        self.inlets = {}
        
    def update_ts(self):
        self.inlets_plt = [v for v in list(self.inlets) 
                            if any([i in v for i in ['Mouse', "mbient", "Audio", "EyeLink"]])]
                            
        plt.ion()
        fig, axs = plt.subplots(len(self.inlets_plt), 1, sharex=False, figsize=(9.16, 9.93))  
        for ax_ith, nm in enumerate(self.inlets_plt):
              axs[ax_ith].set_title(nm)

        axs[-1].set_xticks([])
        mngr = plt.get_current_fig_manager()        
        mngr.window.setGeometry(1015, 30, 905, 1005)        
        fig.tight_layout()
        fig.canvas.draw()        
        fig.show()        
        plt.show(block=False)
        
        sampling = .1
        buff_size = 1024
        mypause(sampling)
        
        print('starting plotting loop')
        while self.pltotting_ts:
            for ax_ith, nm in enumerate(self.inlets_plt):
                inlet = self.inlets[nm]
                tv, ts = inlet.pull_chunk(timeout=0.0)
                if ts == []:
                    continue

                clicks = []
                if "Mouse" in nm:                    
                    clicks = [[its, itv[-1]] for itv, its in zip(tv, ts)if itv[-1] != 0]
                    tv = [itv[:-1] for itv in tv]
                elif "mbient" in nm:
                    # tv = [[np.mean(itv[1:4]), np.mean(itv[4:])] for itv in tv]
                    tv = [[np.mean(itv[1:4])] for itv in tv]
                elif "Audio" in nm:
                    if len(tv[0]) % 2:
                        tv = [[np.max(itv[1:])] for itv in tv]
                    else:
                        tv = [[np.max(itv)] for itv in tv]
                elif "EyeLink" in nm:
                    tv = [[itv[0], itv[3]] for itv in tv]
                tv, ts = np.array(tv), np.array(ts)

                if not hasattr(inlet, "line"):
                    inlet.xdata = np.array(range(buff_size))
                    inlet.ydata = np.zeros((buff_size, tv.shape[1]))
                    inlet.line = axs[ax_ith].plot(inlet.xdata, inlet.ydata)

                inlet.ydata = np.vstack((inlet.ydata[ts.shape[0] - buff_size:-1, :], tv))
                inlet.xdata = np.hstack((inlet.xdata[ts.shape[0] - buff_size:-1], ts))

                for i, chn in enumerate(inlet.ydata.T):
                    inlet.line[i].set_data(inlet.xdata, chn)

                if clicks:
                    for clk in clicks:
                        clr = "g" if clk[1] == 1 else "r" if clk[1] == -1 else "k"
                        axs[ax_ith].axvline(x=clk[0], color=clr)

                axs[ax_ith].set_xlim([max(ts) - (sampling * 50), max(ts)])
                ylim = inlet.ydata.flatten()
                axs[ax_ith].set_ylim([min(ylim), max(ylim)])

            
            if len(self.inlets_plt) == 0:
                self.pltotting_ts = False
                break

            mypause(sampling)

        self.pltotting_ts = False
        plt.close(fig)


def mypause(interval):
    backend = plt.rcParams['backend']
    if backend in matplotlib.rcsetup.interactive_bk:
        figManager = matplotlib._pylab_helpers.Gcf.get_active()
        if figManager is not None:
            canvas = figManager.canvas
            if canvas.figure.stale:
                canvas.draw()
            canvas.start_event_loop(interval)

