# -*- coding: utf-8 -*-
"""
Created on Tue Nov 24 15:41:42 2020

@author: adona
"""
import time

from neurobooth_os import config
from neurobooth_os.iout import metadator as meta


def start_lsl_threads(node_name, collection_id="mvp_025", win=None, conn=None):
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
    kwarg_devs = meta._get_coll_dev_kwarg_tasks(collection_id, conn)
    # Get params from first task
    kward_devs_task1 = kwarg_devs[next(iter(kwarg_devs))]

    streams = {}
    if node_name == "acquisition":
        from neurobooth_os.iout.microphone import MicStream
        from neurobooth_os.iout.camera_intel import VidRec_Intel
        from neurobooth_os.iout.flir_cam import VidRec_Flir

        # streams['micro'] = MicStream()
        for kdev, argsdev in kward_devs_task1.items():
            if "Intel" in kdev:
                streams[kdev] = VidRec_Intel(**argsdev)
            elif "Mbient" in kdev:
                streams[kdev] = connect_mbient(**argsdev)
                if streams[kdev] is None:
                    del streams[kdev]
                else:
                    streams[kdev].start()
            elif "FLIR " in kdev:
                streams[kdev] = VidRec_Flir(**argsdev)
            elif "Mic_Yeti" in kdev:
                streams[kdev] = MicStream(**argsdev)
                streams[kdev].start()

    elif node_name == "presentation":
        from neurobooth_os.iout import marker_stream
        from neurobooth_os.iout.mouse_tracker import MouseStream
        from neurobooth_os.iout.eyelink_tracker import EyeTracker

        streams['mouse'] = MouseStream()
        streams['mouse'].start()
        streams['marker'] = marker_stream()

        for kdev, argsdev in kward_devs_task1.items():
            if 'Eyelink' in kdev:
                streams['Eyelink'] = EyeTracker(win=win, **argsdev)

    elif node_name == "dummy_acq": 
        from neurobooth_os.mock import mock_device_streamer as mock_dev

        for kdev, argsdev in kward_devs_task1.items():
            if "Intel" in kdev:
                streams[kdev] = mock_dev.MockCamera(**argsdev)
            elif "Mbient" in kdev:
                streams[kdev] = mock_dev.MockMbient(**argsdev)

    elif node_name == "dummy_stm":
        from neurobooth_os.iout import marker_stream
        streams['marker'] = marker_stream()

    return streams


def connect_mbient(dev_name="LH", mac='CE:F3:BD:BD:04:8F', try_nmax=5, **kwarg):
    from neurobooth_os.iout.mbient import Sensor

    tinx = 0
    print(f"Trying to connect mbient {dev_name}, mac {mac}")
    while True:
        try:

            sens = Sensor(mac, dev_name, **kwarg)
            return sens
        except Exception as e:
            print(f"Trying to connect mbient {dev_name}, {tinx} out of {try_nmax} tries {e}")
            tinx += 1
            time.sleep(1)
            if tinx >= try_nmax:
                print(f"Failed to connect mbient {dev_name}")
                break


def close_streams(streams):
    for k in list(streams):
        print(f"Closing {k} stream")
        if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
            streams[k].close()
        else:
            streams[k].stop()
        del streams[k]
    return streams


def reconnect_streams(streams):
    for k in list(streams):
        if k.split("_")[0] in ["hiFeed", "Intel", "FLIR"]:
            continue

        if not streams[k].streaming:
            print(f"Re-streaming {k} stream")
            streams[k].start()
        print(f"-OUTLETID-:{k}:{streams[k].oulet_id}")

    return streams
