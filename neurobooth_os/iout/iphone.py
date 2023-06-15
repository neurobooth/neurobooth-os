import os.path as op
from logging import raiseExceptions
from multiprocessing import Condition, Event, RLock
import functools

import socket
import json
import struct
import threading
from datetime import datetime
import select
import uuid
import logging
import time

from neurobooth_os.iout.usbmux import USBMux

global DEBUG_IPHONE
DEBUG_IPHONE = "default"  # 'default', 'verbatim' , 'verbatim_no_lsl', 'default_no_lsl'

if DEBUG_IPHONE in ["default", "verbatim"]:
    from pylsl import StreamInfo, StreamOutlet
    import liesl
    from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


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
        except Exception as e:
            _iphone: IPhone = args[0]
            with _iphone._state_lock:
                _iphone._state = "#ERROR"
            debug_print(f"Error occurred sending/receiving the signal through the socket: {e}")
            _iphone.logger.error(f'iPhone: Error occurred sending/receiving the signal through the socket: {e}')

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
                self._iphone._process_received_message(msg, resp_tag)
                if resp_tag == 0:
                    debug_print(f"Listener received: {msg}")
                else:
                    debug_print(f"Listener received: Tag {resp_tag}")
            except OSError as e:  # Will occur when the socket is closed during shutdown
                if self._running:
                    self.logger.error(f'iPhone: Listening loop encountered an error: {e}')
            except Exception as e:  # Simply log any other errors
                self.logger.error(f'iPhone: Listening loop encountered an error: {e}')
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
    MESSAGE_KEYS = {"MessageType", "SessionID", "TimeStamp", "Message"}

    # decorator for socket_send

    @safe_socket_operation
    def _socket_send(self, packet):
        return self.sock.send(packet)

    @safe_socket_operation
    def _socket_recv(self, nbytes):
        return self.sock.recv(nbytes)

    def __init__(self, name, sess_id="", mock=False, device_id="", sensor_ids=("",)):
        self.connected = False
        self.tag = 0
        self.iphone_sessionID = sess_id
        self.name = name
        self.mock = mock
        self.device_id = device_id
        self.sensor_ids = sensor_ids
        self._state = "#DISCONNECTED"
        self._frame_preview_data = b""
        self._frame_preview_cond = Condition()
        self._dump_video_data = b""
        self._dump_video_cond = Condition()
        self._allmessages = []
        self._message_lock = RLock()
        self._state_lock = RLock()
        self._latest_message = {}
        self._latest_message_type = ''
        self._wait_for_reply_cond = Condition()
        self._timeout_cond = 5
        self.ready_event = Event()  # Used to check if we have re-entered the ready state by ensure_stopped()
        self.streaming = False
        self.streamName = "IPhoneFrameIndex"
        self.outlet_id = str(uuid.uuid4())
        self.logger = logging.getLogger('session')
        self.logger.debug('iPhone: Created Object')

    def _validate_message(self, message, tag):
        if tag == 1:  # TAG==1 corresponds to PREVIEW file receiving
            msg_type = "@PREVIEWRECEIVE"
        elif tag == 2:
            msg_type = "@DUMPRECEIVE"
        elif tag != 0:
            print(f"Incorrect tag received from IPhone. Tag={tag}")
            self.logger.error(f'iPhone: Incorrect tag ({tag}) received.')
            self.disconnect()
            return False
        else:
            if len(message) != len(self.MESSAGE_KEYS):
                print(f"Message has incorrect length: {message}")
                self.logger.error(f'iPhone: Message has incorrect length: {message}')
                self.disconnect()
                return False
            for key in message:
                if key not in self.MESSAGE_KEYS:
                    print(f"Message has incorrect key: {key} not allowed. {message}")
                    self.logger.error(f'iPhone: Message has incorrect key: key={key}; message={message}')
                    self.disconnect()
                    return False
            msg_type = message["MessageType"]
        debug_print(f"Message: {msg_type}")
        return self._update_state(msg_type)

    def _update_state(self, msg_type):
        with self._state_lock:
            debug_print(f"Initial State: {self._state}")
            allowed_trans = self.STATE_TRANSITIONS[self._state]
            if msg_type in allowed_trans:
                prev_state = self._state
                self._state = allowed_trans[msg_type]
                if self._state == '#ERROR':
                    self.logger.error(f'iPhone: Entered #ERROR state from {prev_state} via {msg_type}!')
                elif self._state == '#READY':
                    self.ready_event.set()
            else:
                print(f"Message {msg_type} is not valid in the state {self._state}.")
                self.logger.error(f"iPhone: Message {msg_type} is not valid in the state {self._state}.")
                self.disconnect()
                return False
            debug_print(f"Outcome State:{self._state}")
        return True

    def _message(self, msg_type, ts="", msg=""):
        if msg_type not in self.MESSAGE_TYPES:
            self.logger.error(f'iPhone [state={self._state}]: "{msg_type}" is not an allowed message')
            raise IPhoneError(f'Message type "{msg_type}" not in allowed message type list')
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

    def _sendpacket(self, msg_type, msg_contents=None):
        msg = self._message(msg_type)
        if msg_contents is not None:
            # replace contents of msg with information from provided dict
            for key in msg_contents:
                msg[key] = msg_contents[key]

        if not self._validate_message(msg, 0):  # State transition is side effect of validate_message
            print(f"Message {msg} did not pass validation. Exiting _sendpacket.")
            self.logger.error(f'iPhone [state={self._state}]: Packet Validation Error: {msg}')
            self.disconnect()
            return False

        self._update_message_log(msg, self.tag)
        payload = self._json_wrap(msg).encode("utf-8")
        payload_size = len(payload)
        packet = (
            struct.pack("!IIII", self.VERSION, self.TYPE_MESSAGE, self.tag, payload_size) + payload
        )
        self._socket_send(packet)
        return True

    def _send_and_wait_for_response(self, msg_type, msg_contents=None, wait_on=None):
        with self._wait_for_reply_cond:
            if not self._sendpacket(msg_type, msg_contents=msg_contents):
                self.logger.error(f'iPhone [state={self._state}]: Failed to send {msg_type} packet!')
                return False

            if wait_on is None:
                success = self._wait_for_reply_cond.wait(timeout=self._timeout_cond)
            else:
                success = self._wait_for_reply_cond.wait_for(
                        lambda: self._latest_message_type in wait_on,
                        timeout=self._timeout_cond,
                )

            if not success:
                self.logger.warning(f'iPhone [state={self._state}]: Timeout when waiting for response to {msg_type}.')

            return success

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
        if not ready:
            self.logger.error(f"iPhone [state={self._state}]: Exceeded timeout for packet receipt")
            raise IPhoneError(
                f"Timeout for packet receive exceeded ({timeout_in_seconds} sec)"
            )

        first_frame = self.sock.recv(16)
        version, type, tag, payload_size = struct.unpack("!IIII", first_frame)

        if tag == 1 or tag == 2:
            self._validate_message({}, tag)
            payload = self.recvall(self.sock, payload_size)
            return payload, version, type, tag

        payload = self.sock.recv(payload_size)
        msg = self._json_unwrap(payload)
        self._validate_message(msg, tag)
        return msg, version, type, tag

    def handshake(self, config):
        if self._state != "#DISCONNECTED":
            print("Handshake is only available when disconnected")
            return False

        self.usbmux = USBMux()
        if not self.usbmux.devices:
            self.usbmux.process(0.1)
        if len(self.usbmux.devices) != 1:
            return False

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
        return self._send_and_wait_for_response(
            "@STANDBY",
            msg_contents=msg_camera_config,
            wait_on=self.STATE_TRANSITIONS['#STANDBY'].keys(),
        )

    def _mock_handshake(self):
        tag = self.tag
        self._sendpacket("@STANDBY")
        msg, version, type, resp_tag = self._getpacket()
        self._validate_message(msg)
        if msg["MessageType"] != "@READY":
            self.sock.close()  # close the socket on our side to avoid hanging sockets
            self.logger.error(f"iPhone [state={self._state}]: Cannot establish STANDBY->READY connection")
            raise IPhoneError("Cannot establish STANDBY->READY connection with Iphone")
        return 0

    def start_recording(self, filename):
        msg_filename = {"Message": filename}
        self.logger.debug(f'iPhone [state={self._state}]: Sending @START Message')
        self._send_and_wait_for_response(
            "@START",
            msg_contents=msg_filename,
            wait_on=self.STATE_TRANSITIONS['#START'].keys(),
        )

    def stop_recording(self):
        self.logger.debug(f'iPhone [state={self._state}]: Sending @STOP Message')
        self.ready_event.clear()  # Clear this event so that ensure_stopped() can wait on it
        self._send_and_wait_for_response(
            "@STOP",
            wait_on=["@STOPTIMESTAMP", "@DISCONNECT", "@ERROR"],
        )

    def _update_message_log(self, msg, tag):
        with self._message_lock:
            self._allmessages.append({"message": msg, "ctr_timestamp": str(datetime.now()), "tag": tag})

    def _process_received_message(self, msg, tag):
        if tag == 1:
            with self._frame_preview_cond:
                self._frame_preview_data = msg
                self._frame_preview_cond.notify()
        elif tag == 2:
            with self._dump_video_cond:
                self._dump_video_data = msg
                self._dump_video_cond.notify()
        else:
            self._update_message_log(msg, tag)
            message_type = msg["MessageType"]
            with self._wait_for_reply_cond:
                self._latest_message = msg
                self._latest_message_type = message_type
                self._wait_for_reply_cond.notify()

            if message_type in [
                "@STARTTIMESTAMP",
                "@INPROGRESSTIMESTAMP",
                "@STOPTIMESTAMP",
            ]:
                finfo = eval(msg["TimeStamp"])
                self.fcount = int(finfo["FrameNumber"])
                lsl_sample = [self.fcount, float(finfo["Timestamp"]), time.time()]
                self.lsl_push_sample(lsl_sample)
                debug_print(lsl_sample)

    @debug_lsl
    def createOutlet(self):
        info = set_stream_description(
            stream_info=StreamInfo(
                name=self.streamName,
                type="videostream",
                channel_format="double64",
                channel_count=3,
                source_id=self.outlet_id,
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
        print(f"-OUTLETID-:{self.streamName}:{self.outlet_id}")
        return StreamOutlet(info)

    @debug_lsl
    def lsl_push_sample(self, *args):
        self.outlet.push_sample(*args)

    @debug_lsl
    def lsl_print(self, *args):
        print(*args)

    def frame_preview(self):
        self.logger.debug(f'iPhone [state={self._state}]: Sending @PREVIEW Message')
        with self._frame_preview_cond:
            self._frame_preview_data = b""
            if self._sendpacket("@PREVIEW"):
                self._frame_preview_cond.wait(timeout=self._timeout_cond)
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

    def dump(self, filename, timeout_sec=None):
        if timeout_sec is None:
            timeout_sec = self._timeout_cond
        success = False

        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMP Message')
        with self._dump_video_cond:
            self._dump_video_data = b""
            if self._sendpacket("@DUMP", msg_contents={"Message": filename}):
                success = self._dump_video_cond.wait(timeout=timeout_sec)
            return success, self._dump_video_data

    def dumpsuccess(self, filename):
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMPSUCCESS Message')
        return self._sendpacket("@DUMPSUCCESS", msg_contents={"Message": filename})

    def disconnect(self):
        if self._state == "#DISCONNECTED":
            print("IPhone device is already disconnected")
            return False
        self.logger.debug(f'iPhone [state={self._state}]: Disconnecting')
        self._sendpacket("@DISCONNECT")
        time.sleep(4)
        self._listen_thread.stop()
        self.sock.close()  # Closing the socket will force an error that will break the thread out of its wait
        self._listen_thread.join(timeout=3)
        if self._listen_thread.is_alive():
            self.logger.error(f'iPhone [state={self._state}]: Could not stop listening thread.')
            raise IPhoneError("Cannot stop the recording thread")
        self.connected = False
        self.streaming = False
        return True

    def dumpall_getfilelist(self, log_files: bool = True):
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMPALL Message')
        with self._wait_for_reply_cond:
            if not self._sendpacket("@DUMPALL"):
                return None

            if not self._wait_for_reply_cond.wait_for(
                lambda: self._latest_message_type in self.STATE_TRANSITIONS['#DUMPALL'].keys(),
                timeout=self._timeout_cond,
            ):
                self.logger.error('Timeout when waiting for @@FILESTODUMP.')
                return None

            filelist = self._latest_message["Message"]
            if self._state == "#ERROR":
                self.logger.error(f'iPhone [state={self._state}]: @DUMPALL Error; message="{filelist}"')
                return None

            if log_files:
                self.logger.debug(f"iPhone [state={self._state}]: File List (N={len(filelist)}) = {filelist}")

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
        help='The folder the LSL stream should record to.',
    )
    parser.add_argument(
        '--no-plots',
        dest='show_plots',
        action='store_false',
        help='Disable plotting of results.',
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
    task_id = f'{args.subject_id}_{date}_task_obs_1'

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
    print(f"mean diff diff: {np.mean(np.abs(df_pc[1:] - df_ip[1:]))}")

    if args.show_plots:
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

        tstmp = data[0]["time_stamps"]
        plt.hist(np.diff(tstmp[1:]) - np.diff(ts_ip[1:]))

        plt.figure()
        plt.hist(df_ip, 50)
