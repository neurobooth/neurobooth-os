# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""
import time

from neurobooth_os import config
from neurobooth_os.iout import metadator as meta

from mbientlab.warble import BleScanner
from time import sleep




def scann_BLE():
    print("scanning for devices...")
    devices = {}
    def handler(result):
        devices[result.mac] = result.name
    
    BleScanner.set_handler(handler)
    BleScanner.start()
    
    sleep(10.0)
    BleScanner.stop()
        
    
    
def start_lsl_threads(node_name, collection_id="mvp_030", win=None, conn=None):
    """ Initiate devices and LSL streams based on databased parameters.

    Parameters
    ----------
    node_name : str
        Name of the server where to start the lsl threads
    collection_id : str, optional
        Name of studies collection in the database, by default "mvp_025"
    win : object, optional
        Pycharm window, by default None
    conn : object, optional
        Connector to the database, by default None

    Returns
    -------
    dict of streams
        Contains the name of the device and device class
    """

    if conn is None:
        print("getting conn")
        conn = meta.get_conn()

    # Get params from all tasks
    kwarg_devs = meta._get_device_kwargs_by_task(collection_id, conn)
    # Get all device params from session
    kwarg_alldevs = {}
    for dc in kwarg_devs.values():
        kwarg_alldevs.update(dc)
        
    scann_BLE()

    streams = {}
    if node_name == "acquisition":
        from neurobooth_os.iout.microphone import MicStream
        from neurobooth_os.iout.camera_intel import VidRec_Intel
        from neurobooth_os.iout.flir_cam import VidRec_Flir
        from neurobooth_os.iout.iphone import IPhone
        
        for kdev, argsdev in kwarg_alldevs.items():
            if "Intel" in kdev:
                streams[kdev] = VidRec_Intel(**argsdev)
            elif "Mbient" in kdev:
                # Don't connect mbients from STM
                if any([d in kdev for d in ["Mbient_LF", "Mbient_RF"]]):                    
                    continue
                streams[kdev] = connect_mbient(**argsdev)
                if streams[kdev] is None:
                    del streams[kdev]
                else:
                    streams[kdev].start()
            elif "FLIR" in kdev:
                streams[kdev] = VidRec_Flir(**argsdev)
            elif "Mic_Yeti" in kdev:
                streams[kdev] = MicStream(**argsdev)
                # streams[kdev].start()
            elif "IPhone"in kdev:
                success = False
                streams[kdev] = IPhone(name='IPhoneFrameIndex', **argsdev)
                success = streams[kdev].prepare()
                if not success and streams.get(kdev) is not None:
                    del streams[kdev]

    elif node_name == "presentation":
        from neurobooth_os.iout import marker_stream
        from neurobooth_os.iout.mouse_tracker import MouseStream
        from neurobooth_os.iout.eyelink_tracker import EyeTracker

        streams['marker'] = marker_stream()

        for kdev, argsdev in kwarg_alldevs.items():
            if 'Eyelink' in kdev:
                streams['Eyelink'] = EyeTracker(win=win, **argsdev)
            elif 'Mouse' in kdev:
                streams['mouse'] = MouseStream(**argsdev)
                streams['mouse'].start()
            
            elif any([d in kdev for d in ["Mbient_LF", "Mbient_RF"]]):
                streams[kdev] = connect_mbient(**argsdev)
                if streams[kdev] is None:
                    del streams[kdev]
                else:
                    streams[kdev].start()
                    

    elif node_name == "dummy_acq": 
        from neurobooth_os.mock import mock_device_streamer as mock_dev
        from neurobooth_os.iout.iphone import IPhone
        
        for kdev, argsdev in kwarg_alldevs.items():
            if "Intel" in kdev:
                streams[kdev] = mock_dev.MockCamera(**argsdev)
            elif "Mbient" in kdev:
                streams[kdev] = mock_dev.MockMbient(**argsdev)
                streams[kdev].start()
            elif "IPhone"in kdev:
                success = False
                streams[kdev] = IPhone(name='IPhoneFrameIndex', **argsdev)
                success = streams[kdev].prepare()
                if not success and streams.get(kdev) is not None:
                    del streams[kdev]

    elif node_name == "dummy_stm":
        from neurobooth_os.iout import marker_stream
        streams['marker'] = marker_stream()

    return streams


def connect_mbient(dev_name="LH", mac='CE:F3:BD:BD:04:8F', try_nmax=5, **kwarg):
    from neurobooth_os.iout.mbient import Sensor, reset_mbient

    tinx = 0
    print(f"Trying to connect mbient {dev_name}, mac {mac}")
    while True:
        try:
            sens = Sensor(mac, dev_name, **kwarg)
            return sens
        except Exception as e:
            print(f"Trying to connect mbient {dev_name}, {tinx} out of {try_nmax} tries {e}")
            tinx += 1            
            if tinx >= try_nmax:
                try: 
                    reset_mbient(mac, dev_name)
                    sens = Sensor(mac, dev_name, **kwarg)
                    return sens
                except:
                    print(f"Failed to connect mbient {dev_name}")
                break
            time.sleep(1)


def close_streams(streams):
    for k in list(streams):
        print(f"Closing {k} stream")
        if k.split("_")[0] in ["hiFeed", "Intel", "FLIR", "IPhone"]:
            streams[k].close()
        else:
            streams[k].stop()
        # del streams[k]
    return streams


def reconnect_streams(streams):
    for k in list(streams):
        if k.split("_")[0] in ["hiFeed", "Intel", "FLIR", "IPhone"]:
            continue

        if not streams[k].streaming:
            print(f"Re-streaming {k} stream")
            streams[k].start()
        print(f"-OUTLETID-:{k}:{streams[k].oulet_id}")

    return streams
