# -*- coding: utf-8 -*-
"""
Created on Tue Feb  2 17:01:43 2021

@author: adona
"""

#!/usr/bin/env python
"""
ReceiveAndPlot example for LSL
This example shows data from all found outlets in realtime.
It illustrates the following use cases:
- efficiently pulling data, re-using buffers
- automatically discarding older samples
- online postprocessing
"""

import numpy as np
import math
import pylsl
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtGui
from typing import List
import cv2
from datetime import datetime

# Basic parameters for the plotting window
plot_duration = 5  # how many seconds of data to show
update_interval = 60  # ms between screen updates
pull_interval = 1/20  # ms between each pull operation


class Inlet:
    """Base class to represent a plottable inlet"""
    def __init__(self, info: pylsl.StreamInfo):
        # create an inlet and connect it to the outlet we found earlier.
        # max_buflen is set so data older the plot_duration is discarded
        # automatically and we only pull data new enough to show it

        # Also, perform online clock synchronization so all streams are in the
        # same time domain as the local lsl_clock()
        # (see https://labstreaminglayer.readthedocs.io/projects/liblsl/ref/enums.html#_CPPv414proc_clocksync)
        # and dejitter timestamps
        self.inlet = pylsl.StreamInlet(info, max_buflen=plot_duration,
                                       processing_flags=pylsl.proc_clocksync | pylsl.proc_dejitter)
        # store the name and channel count
        self.name = info.name()
        self.channel_count = info.channel_count()

    def pull_and_plot(self, plot_time: float, plt: pg.PlotItem):
        """Pull data from the inlet and add it to the plot.
        :param plot_time: lowest timestamp that's still visible in the plot
        :param plt: the plot the data should be shown on
        """
        # We don't know what to do with a generic inlet, so we skip it.
        pass


class VideoInlet(Inlet):
    """A DataInlet represents an inlet with frame images."""
    dtypes = [[], np.float32, np.float64, None, np.int32, np.int16, np.int8, np.int64]

    def __init__(self, info: pylsl.StreamInfo, plt: pg.PlotItem):
        super().__init__(info)
        # calculate the size for our buffer, i.e. two times the displayed data
        plt.setAspectLocked(True)
        self.img = pg.ImageItem(border='w')
        plt.addItem( self.img )
        
        self.img.setImage(np.empty([640, 480], dtype=np.uint8 ))
        
        
    def pull_and_plot(self):
        # pull the data
        frame, timstmp = self.inlet.pull_sample(timeout=0.0)
        # ts will be empty if no samples were pulled, a list of timestamps otherwise
        if frame:                    
                    
            img_frame = np.array(frame, dtype=np.uint8).reshape(480, 640)
            
            
            cv2.putText(img_frame,  
            f'    {datetime.now().strftime("%H:%M:%S.%f")}',  
            (0, 75),  
            cv2.FONT_HERSHEY_SIMPLEX , 1,  
            (0, 0, 0), 2, cv2.LINE_4) 
            
            
            self.img .setImage(img_frame.T[:, ::-1])
               


class MarkerInlet(Inlet):
    """A MarkerInlet shows events that happen sporadically as vertical lines"""
    def __init__(self, info: pylsl.StreamInfo):
        super().__init__(info)

    def pull_and_plot(self, plot_time, plttrs):
        # TODO: purge old markers
        strings, timestamps = self.inlet.pull_chunk(0)
        if timestamps:            
                for string, ts in zip(strings, timestamps):
                    plttrs.addItem(pg.InfiniteLine(320, angle=90, movable=False, label=string[0]))



def main():
    # firstly resolve all streams that could be shown
    inlets: List[Inlet] = []
    plttrs = {}
    print("looking for streams")
    streams = pylsl.resolve_streams()



    app = QtGui.QApplication([])
    
    ## Create window with GraphicsView widget
    win = pg.GraphicsLayoutWidget()
    win.show()  ## show widget alone in its own window
    win.setWindowTitle('LSL video plotter')
    
 

    win.show()

    # plt.enableAutoRange(x=False, y=True)

    # iterate over found streams, creating specialized inlet objects that will
    # handle plotting the data
    
    for info in streams:          
        if info.type() == 'MarkersX':
            if info.nominal_srate() != pylsl.IRREGULAR_RATE \
                    or info.channel_format() != pylsl.cf_string:
                print('Invalid marker stream ' + info.name())
            print('Adding marker inlet: ' + info.name())
            inlets.append(MarkerInlet(info))
        # elif info.nominal_srate() != pylsl.IRREGULAR_RATE \
        #         and info.channel_format() != pylsl.cf_string:
            
        elif info.name()[:-2]  == "CamStream":
            print('Adding data inlet: ' + info.name())
            
            name = info.name() 
            # store widget in dic for later
            view = win.addViewBox()

            plttrs[name]= view
       
            inlets.append(VideoInlet(info, plttrs[name]))



    def update():
        # Read data from the inlet. Use a timeout of 0.0 so we don't block GUI interaction.
        mintime = pylsl.local_clock() - plot_duration
        # call pull_and_plot for each inlet.
        # Special handling of inlet types (markers, continuous data) is done in
        # the different inlet classes.
        for inlet in inlets:
            if inlet.name in ['Marker', 'Markers']:
                
                for plt in plttrs.values():                    
                    inlet.pull_and_plot(mintime, plt)
            else:
                inlet.pull_and_plot()


    # create a timer that will pull and add new data occasionally
    pull_timer = QtCore.QTimer()
    pull_timer.timeout.connect(update)
    pull_timer.start(pull_interval)

    import sys

    # Start Qt event loop unless running in interactive mode or using pyside.
    if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
        QtGui.QApplication.instance().exec_()


if __name__ == '__main__':
    main()