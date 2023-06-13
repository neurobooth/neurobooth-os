import os.path as op
from email import message_from_string
from functools import partial
from logging import raiseExceptions
from multiprocessing import Condition
import matplotlib

import socket
import json
import struct
import threading
import time
from datetime import datetime
import select
import uuid
import logging

from neurobooth_os.iout.usbmux import USBMux

global DEBUG_IPHONE
DEBUG_IPHONE = "default"  # 'default', 'verbatim' , 'verbatim_no_lsl', 'default_no_lsl'

if DEBUG_IPHONE in ["default", "verbatim"]:
    from pylsl import StreamInfo, StreamOutlet
    import liesl
    from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


import functools

# decorator for debug printing
def debug(func):
    @functools.wraps(func)
    def wrapper_print_debug(*args, **kwargs):
        global DEBUG_IPHONE
        if DEBUG_IPHONE in ["verbatim", "verbatim_no_lsl"]:
            func(*args, **kwargs)

    return wrapper_print_debug


# decorator for lsl streaming
def debug_lsl(func):
    @functools.wraps(func)
    def wrapper_lsl_debug(*args, **kwargs):
        global DEBUG_IPHONE
        if DEBUG_IPHONE in ["default", "verbatim"]:
            return func(*args, **kwargs)
        else:
            return None

    return wrapper_lsl_debug


@debug
def debug_print(arg):
    print(arg)


def safe_socket_operation(func):
    @functools.wraps(func)
    def wrapper_safe_socket(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:
            args[0]._state = "#ERROR"
            debug_print("Error occured at sending/receiving the signal through socket")

    return wrapper_safe_socket


IPHONE_PORT = (
    2345  # IPhone should have socket on this port open, if we're connecting to it.
)


class IPhoneError(Exception):
    pass


class IPhoneListeningThread(threading.Thread):
    def __init__(self, *args):
        self._iphone = args[0]
        self._running = True
        self.logger = logging.getLogger('session')
        threading.Thread.__init__(self)

    def run(self):
        self.logger.debug('iPhone: Entering Listening Loop')
        while self._running:
            try:
                msg, version, type, resp_tag = self._iphone._getpacket()
                self._iphone._process_message(msg, resp_tag)
                if resp_tag == 0:
                    debug_print(f"Listener received: {msg}")
                else:
                    debug_print(f"Listener received: Tag {resp_tag}")
            except:
                pass
        self.logger.debug('iPhone: Exiting Listening Loop')

    def stop(self):
        self._running = False


class IPhone:
    TYPE_MESSAGE = 101
    VERSION = 1
    STATE_TRANSITIONS = {
        "#DISCONNECTED": {"@HANDSHAKE": "#CONNECTED", "@ERROR": "#ERROR"},
        "#CONNECTED": {
            "@STANDBY": "#STANDBY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#PREVIEW": {
            "@PREVIEWRECEIVE": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#DUMPALL": {
            "@FILESTODUMP": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },  # NO SPECIAL state for after received ready to dump. Dump is done from 'Connected' state
        "#DUMP": {
            "@DUMPRECEIVE": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#STANDBY": {
            "@READY": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#READY": {
            "@START": "#START",
            "@PREVIEW": "#PREVIEW",
            "@DUMPALL": "#DUMPALL",
            "@DUMP": "#DUMP",
            "@DUMPSUCCESS": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
            "@INPROGRESSTIMESTAMP": "#READY"
        },
        "#START": {
            "@STARTTIMESTAMP": "#RECORDING",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#RECORDING": {
            "@INPROGRESSTIMESTAMP": "#RECORDING",
            "@STOP": "#STOP",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#STOP": {
            "@STOPTIMESTAMP": "#READY",
            "@INPROGRESSTIMESTAMP": "#STOP",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#ERROR": {"@DISCONNECT": "#DISCONNECTED"},
    }
    MESSAGE_TYPES = []
    for elem in STATE_TRANSITIONS:
        MESSAGE_TYPES += STATE_TRANSITIONS[elem].keys()
    MESSAGE_TYPES = set(MESSAGE_TYPES)
    #    print(MESSAGE_TYPES)
    #    MESSAGE_TYPES=set(['@START','@STOP','@STANDBY','@READY','@PREVIEW','@DUMP','@STARTTIMESTAMP','@INPROGRESSTIMESTAMP','@STOPTIMESTAMP','@DUMPALL','@DISCONNECT','@FILESTODUMP'])
    MESSAGE_KEYS = set(["MessageType", "SessionID", "TimeStamp", "Message"])

    # decorator for socket_send

    @safe_socket_operation
    def _socket_send(self, packet):
        return self.sock.send(packet)

    @safe_socket_operation
    def _socket_recv(self, nbytes):
        return self.sock.recv(nbytes)

    def __init__(self, name, sess_id="", mock=False, device_id="", sensor_ids=("",)):
        self.connected = False
        self.recording = False
        self.tag = 0
        self.iphone_sessionID = sess_id
        self._allmessages = []
        self.name = name
        self.mock = mock
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self._state = "#DISCONNECTED"
        self._frame_preview_data = b""
        self._frame_preview_cond = Condition()
        self._dump_video_data = b""
        self._dump_video_cond = Condition()
        self._wait_for_reply_cond = Condition()
        self._msg_latest = {}
        self._timeout_cond = 5
        self.streaming = False
        self.streamName = "IPhoneFrameIndex"
        self.oulet_id = str(uuid.uuid4())
        self.ready_event = threading.Event()  # Used to check if we have re-entered the ready state by ensure_stopped()
        self.logger = logging.getLogger('session')
        self.logger.debug('iPhone: Created Object')

    def _validate_message(self, message, tag):

        if tag == 1:  # TAG==1 corresponds to PREVIEW file receiving
            msgType = "@PREVIEWRECEIVE"
        elif tag == 2:
            msgType = "@DUMPRECEIVE"
        elif tag != 0:
            print(f"Incorrect tag received from IPhone. Tag={tag}")
            self.disconnect()
            return False
            # raise IPhoneError(f'Incorrect tag received from IPhone. Tag={tag}')
        else:
            if len(message) != len(self.MESSAGE_KEYS):
                print(f"Message has incorrect length: {message}")
                self.disconnect()
                return False
                # raise IPhoneError(f'Message has incorrect length: {message}')
            for key in message:
                if key not in self.MESSAGE_KEYS:
                    print(f"Message has incorrect key: {key} not allowed. {message}")
                    self.disconnect()
                    return False
                    # raise IPhoneError(f'Message has incorrect key: {key} not allowed. {message}')
            msgType = message["MessageType"]
        debug_print(f"Initial State: {self._state}")
        debug_print(f"Message: {msgType}")
        # if msgType in ['@STARTTIMESTAMP', '@INPROGRESSTIMESTAMP','@STOPTIMESTAMP']:
        #     print('Correct msg type')
        #     debug_print(f'Message: {message}')
        # validate whether the transition is valid
        allowed_trans = self.STATE_TRANSITIONS[self._state]
        if msgType in allowed_trans:
            prev_state = self._state
            self._state = allowed_trans[msgType]
            if self._state == '#ERROR':
                self.logger.error(f'iPhone: Entered #ERROR state from {prev_state} via {msgType}!')
            elif self._state == '#READY':
                self.ready_event.set()
        else:
            print(f"Message {msgType} is not valid in the state {self._state}.")
            self.logger.error(f"iPhone: Message {msgType} is not valid in the state {self._state}.")
            self.disconnect()
            return False
            # raise IPhoneError(f'Message {msgType} is not valid in the state {self._state}.')
        debug_print(f"Outcome State:{self._state}")
        return True

    def _message(self, msg_type, ts="", msg=""):
        if not msg_type in self.MESSAGE_TYPES:
            self.logger.error(f'iPhone [state={self._state}]: "{msg_type}" is not an allowed message')
            raise IPhoneError(
                f'Message type "{msg_type}" not in allowed message type list'
            )
        return {
            "MessageType": msg_type,
            "SessionID": self.iphone_sessionID,
            "TimeStamp": ts,
            "Message": msg,
        }

    def _json_wrap(self, message):
        json_msg = json.dumps(message)
        json_msg = "####" + json_msg  # add 4 bytes
        return json_msg

    def _json_unwrap(self, payload):
        message = json.loads(payload[4:])
        return message

    def _sendpacket(self, msg_type, msg_contents=None, cond=None):
        #        if not self.connected:
        #            raise IPhoneError('IPhone is not connected')
        msg = self._message(msg_type)
        if not msg_contents is None:
            # replace contents of msg with information from provided dict
            for key in msg_contents:
                msg[key] = msg_contents[key]
        if not self._validate_message(msg, 0):
            print(f"Message {msg} did not pass validation. Exiting _sendpacket.")
            self.logger.error(f'iPhone [state={self._state}]: Packet Validation Error: {msg}')
            self.disconnect()
            return False
            # do transition through validate_message
        self._process_message(msg, self.tag)
        payload = self._json_wrap(msg).encode("utf-8")
        payload_size = len(payload)
        packet = (
            struct.pack("!IIII", self.VERSION, self.TYPE_MESSAGE, self.tag, payload_size) + payload
        )

        if not cond is None:
            cond.acquire()
            self._socket_send(packet)
            # self.sock.send(packet)
            if not cond.wait(timeout=self._timeout_cond):
                cond.release()
                print(f"No reply received from the device after packet {msg_type} was sent.")
                # self.disconnect()
                return False
            cond.release()
        else:
            self._socket_send(packet)
            # self.sock.send(packet)
        return True

    def recvall(self, sock, n):
        # Helper function to recv n bytes or return None if EOF is hit
        fragments = []
        BUFF_SIZE = 16384
        MAX_RECV = 130992
        buff_recv = 0
        while True:
            bytes_to_pull = n
            if (n - buff_recv) < MAX_RECV:
                bytes_to_pull = n - buff_recv
            packet = sock.recv(bytes_to_pull)
            # packet = self._socket_recv(bytes_to_pull)

            buff_recv += len(packet)
            fragments.append(packet)
            if buff_recv >= n:
                break
        data = b"".join(fragments)
        return data

    def _getpacket(self, timeout_in_seconds=20):
        ready, _, _ = select.select([self.sock], [], [], timeout_in_seconds)
        # print(ready)
        if ready:
            # first_frame=self._socket_recv(16)
            first_frame = self.sock.recv(16)
            version, type, tag, payload_size = struct.unpack("!IIII", first_frame)

            if tag == 1 or tag == 2:
                self._validate_message({}, tag)
                payload = self.recvall(self.sock, payload_size)
                return payload, version, type, tag
            else:
                # payload= self._socket_recv(payload_size)
                payload = self.sock.recv(payload_size)

            msg = self._json_unwrap(payload)
            self._validate_message(msg, tag)
            return msg, version, type, tag
        else:
            self.logger.error(f"iPhone [state={self._state}]: Exceed timeout for packet receipt")
            raise IPhoneError(
                f"Timeout for packet receive exceeded ({timeout_in_seconds} sec)"
            )

    def handshake(self, config):
        if self._state != "#DISCONNECTED":
            print("Handshake is only available when disconnected")
            return False
        self.usbmux = USBMux()
        if not self.usbmux.devices:
            self.usbmux.process(0.1)
        # for dev in self.usbmux.devices:
        #     print(dev)
        if len(self.usbmux.devices) == 1:
            self.device = self.usbmux.devices[0]
            try:
                self.sock = self.usbmux.connect(self.device, IPHONE_PORT)
            except:
                return False
            self._state = "#CONNECTED"

            # as soon as we're connected - start parallel listening thread.
            self._listen_thread = IPhoneListeningThread(self)
            self._listen_thread.start()
            # self.sock.setblocking(0)
            self.connected = True
            #            self.notifyonframe=1
            # Create config

            msg_camera_config = {"Message": json.dumps(config)}
            print(msg_camera_config)
            self._sendpacket(
                "@STANDBY",
                msg_contents=msg_camera_config,
                cond=self._wait_for_reply_cond,
            )
            return True
        else:
            return False

    def _mock_handshake(self):
        tag = self.tag
        self._sendpacket("@STANDBY")
        msg, version, type, resp_tag = self._getpacket()
        self._validate_message(msg)
        if msg["MessageType"] != "@READY":
            self.sock.close()  # close the socket on our side to avoid hanging sockets
            self.logger.error(f"iPhone [state={self._state}]: Cannot establish STANDBY->READY connection")
            raise IPhoneError("Cannot establish STANDBY->READY connection with Iphone")
        # if tag!=resp_tag (check with Steven)
        # process message - send timestamps to LSL, etc.
        self._process_message(msg, resp_tag)
        return 0

    def start_recording(self, filename):
        #        if not self.connected:
        #            raise IPhoneError('IPhone not connected when start_recording is called.')
        #        tag=self.tag
        msg_filename = {"Message": filename}
        self.logger.debug(f'iPhone [state={self._state}]: Sending @START Message')
        self._sendpacket(
            "@START", msg_contents=msg_filename, cond=self._wait_for_reply_cond
        )
        return 0

    def stop_recording(self):
        self.logger.debug(f'iPhone [state={self._state}]: Sending @STOP Message')
        self.ready_event.clear()  # Clear this event so that ensure_stopped() can wait on it
        self._sendpacket("@STOP", cond=self._wait_for_reply_cond)
        return 0

    def _process_message(self, msg, tag):
        if tag == 1:
            self._frame_preview_cond.acquire()
            self._frame_preview_data = msg
            self._frame_preview_cond.notify()
            self._frame_preview_cond.release()
        #            return msg #msg is binary data - image
        elif tag == 2:
            self._dump_video_cond.acquire()
            self._dump_video_data = msg
            self._dump_video_cond.notify()
            self._dump_video_cond.release()
        #            return msg #msg is binary data - video
        else:
            self._wait_for_reply_cond.acquire()
            self._msg_latest = msg
            self._allmessages.append(
                {"message": msg, "ctr_timestamp": str(datetime.now()), "tag": tag})

            if msg["MessageType"] in [
                "@STARTTIMESTAMP",
                "@INPROGRESSTIMESTAMP",
                "@STOPTIMESTAMP",
            ]:
                finfo = eval(msg["TimeStamp"])
                self.fcount = int(finfo["FrameNumber"])
                debug_print([self.fcount, float(finfo["Timestamp"]), time.time()])
                self.lsl_push_sample([self.fcount, float(finfo["Timestamp"]), time.time()])
                if msg["MessageType"] == "@INPROGRESSTIMESTAMP":
                    if self._state == "#RECORDING":
                        self._wait_for_reply_cond.notify()
                else:
                    self._wait_for_reply_cond.notify()
            self._wait_for_reply_cond.release()

    @debug_lsl
    def createOutlet(self):
        info = set_stream_description(
            stream_info=StreamInfo(
                name=self.streamName,
                type="videostream",
                channel_format="double64",
                channel_count=3,
                source_id=self.oulet_id,
            ),
            device_id=self.device_id,
            sensor_ids=self.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['FrameNum', 'Time_iPhone', 'Time_ACQ'],
            column_desc={
                'FrameNum': 'App-tracked frame number',
                'Time_iPhone': 'App timestamp (s)',
                'Time_ACQ': 'Local machine timestamp (s)',
            }
        )
        print(f"-OUTLETID-:{self.streamName}:{self.oulet_id}")
        return StreamOutlet(info)

    @debug_lsl
    def lsl_push_sample(self, *args):
        self.outlet.push_sample(*args)

    @debug_lsl
    def lsl_print(self, *args):
        print(*args)

    def frame_preview(self):
        self._frame_preview_data = b""
        self._sendpacket("@PREVIEW", cond=self._frame_preview_cond)
        return self._frame_preview_data

    def start(self, filename):
        self.streaming = True
        filename += "_IPhone"
        filename = op.split(filename)[-1]
        self.lsl_print(f"-new_filename-:{self.streamName}:{filename}.mov")
        time.sleep(0.05)
        self.lsl_print(f"-new_filename-:{self.streamName}:{filename}.json")
        self.start_recording(filename)

    def stop(self):
        self.stop_recording()
        self.streaming = False

    def close(self):
        self.disconnect()

    def ensure_stopped(self, timeout_seconds: float) -> None:
        """Check to make sure that we have transitioned from the #STOP state back to the #READY state."""
        success = self.ready_event.wait(timeout=timeout_seconds)
        if not success:
            self.logger.error(
                f'iPhone [state={self._state}]: Ready state not reached during stop sequence before timeout!'
            )
            raise IPhoneError('Ready state not reached during stop sequence before timeout!')

        self.logger.debug(f'iPhone [state={self._state}]: Transition to #READY Detected')

    def log_files(self) -> None:
        """Add the files currently in the iPhone's memory to the log"""
        files = self.dumpall_getfilelist(print_files=False)
        self.logger.debug(f"iPhone [state={self._state}]: File List = {str(files)}")

    def prepare(self, mock=False, config=None):
        if mock:
            HOST = "127.0.0.1"  # Symbolic name meaning the local host
            PORT = 50009  # Arbitrary non-privileged port
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))
            self.sock = s
            self._mock_handshake()
            self.connected = True
        else:
            if config is None:
                self.notifyonframe = 1
                config = {
                    "NOTIFYONFRAME": str(self.notifyonframe),
                    "VIDEOQUALITY": "1920x1080",
                    "USECAMERAFACING": "BACK",
                    "FPS": "240",
                    "BRIGHTNESS": "50",
                    "LENSPOS": "0.7",
                }
            self.notifyonframe = int(config["NOTIFYONFRAME"])
            connected = self.handshake(config)
            if connected:
                self.outlet = self.createOutlet()
                self.streaming = True
            return connected

    def dump(self, filename):
        self._dump_video_data = b""
        msg_filename = {"Message": filename}
        print(f'DUMPING: {filename}')
        self._sendpacket("@DUMP", msg_filename, cond=self._dump_video_cond)
        return self._dump_video_data

    def dumpsuccess(self, filename):
        msg_filename = {"Message": filename}
        self._sendpacket("@DUMPSUCCESS", msg_filename)
        return True

    def disconnect(self):
        if self._state == "#DISCONNECTED":
            print("IPhone device is already disconnected")
            return False
        self.logger.debug(f'iPhone [state={self._state}]: Disconnecting')
        self._sendpacket("@DISCONNECT")
        time.sleep(4)
        self.sock.close()
        self._listen_thread.stop()
        self._listen_thread.join(timeout=3)
        if self._listen_thread.is_alive():
            self.logger.error(f'iPhone [state={self._state}]: Could not stop listening thread.')
            raise IPhoneError("Cannot stop the recording thread")
        self.connected = False
        self.streaming = False
        return True

    def dumpall_getfilelist(self, print_files: bool = True):
        self._sendpacket("@DUMPALL", cond=self._wait_for_reply_cond)
        filelist = self._msg_latest["Message"]
        if print_files:
            print(f'FILELIST: {filelist}')
        if self._state == "#ERROR":
            return None
        return filelist


if __name__ == "__main__":

    @debug_lsl
    def liesl_sesion_create(**kwargs):
        session = liesl.Session(**kwargs)
        return session

    @debug_lsl
    def liesl_sesion_start(session):
        session.start_recording()

    @debug_lsl
    def liesl_sesion_stop(session):
        session.stop_recording()

    import time
    import argparse

    parser = argparse.ArgumentParser(description='Run a standalone capture using the iPhone.')
    parser.add_argument(
        '--duration',
        default=1,
        type=int,
        help='Duration of video capture'
    )
    parser.add_argument(
        '--subject-id',
        default='007',
        type=str,
        help='The subject ID to use',
    )
    parser.add_argument(
        '--recording-folder',
        default='',
        type=str,
        help='The folder the LSL stream should record to.'
    )
    args = parser.parse_args()


    # Creating and starting mock streams:

    # config={'NOTIFYONFRAME':'1',
    #                        'VIDEOQUALITY':'3840x2160',
    #                        'USECAMERAFACING':'BACK','FPS':'60'}

    # config={'NOTIFYONFRAME':'1',
    #                        'VIDEOQUALITY':'1920x1080',
    #                        'USECAMERAFACING':'BACK','FPS':'120 or 240'}
    iphone = IPhone("iphone")
    config = {
        "NOTIFYONFRAME": "1",
        "VIDEOQUALITY": "1920x1080",
        "USECAMERAFACING": "BACK",
        "FPS": "240",
        "BRIGHTNESS": "50",
        "LENSPOS": "0.7",
    }

    if not iphone.prepare(config=config):
        print("Could not connect to iphone")

    frame = iphone.frame_preview()

    streamargs = {"name": "IPhoneFrameIndex"}
    date = datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")
    task_id = f'{args.subject_id}_{date}_task_obs_1_IPhone'

    # Start LSL
    session = liesl_sesion_create(
        prefix=args.subject_id, streamargs=[streamargs], mainfolder=args.recording_folder
    )
    liesl_sesion_start(session)

    # Data capture
    iphone.start(task_id)
    time.sleep(args.duration)
    iphone.stop()

    # Stop LSL
    liesl_sesion_stop(session)

    iphone.disconnect()

    import pyxdf
    import glob
    import numpy as np

    fname = glob.glob(f"{args.subject_id}/recording_R0*.xdf")[-1]
    data, header = pyxdf.load_xdf(fname)

    ts = data[0]["time_series"]
    ts_pc = [t[1] for t in ts]
    ts_ip = [t[2] for t in ts]

    df_pc = np.diff(ts_pc)
    df_ip = np.diff(ts_ip)

    import matplotlib.pyplot as plt

    plt.figure()
    plt.plot(df_pc)
    plt.plot(df_ip)
    plt.show()

    plt.figure()
    plt.scatter(df_pc, df_ip)

    plt.show()

    plt.figure()
    plt.hist(np.diff(ts_pc[1:]) - np.diff(ts_ip[1:]), 20)

    print("mean diff diff ", np.mean(np.abs(np.diff(ts_pc[1:]) - np.diff(ts_ip[1:]))))

    tstmp = data[0]["time_stamps"]
    plt.hist(np.diff(tstmp[1:]) - np.diff(ts_ip[1:]))

    plt.figure()
    plt.hist(df_ip, 50)
