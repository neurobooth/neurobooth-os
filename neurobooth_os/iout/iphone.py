import os.path as op
import sys
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
from typing import Dict, List, Tuple, Any, Optional, Union, ByteString

from neurobooth_os.iout.usbmux import USBMux

global DEBUG_IPHONE
DEBUG_IPHONE = "default"  # 'default', 'verbatim' , 'verbatim_no_lsl', 'default_no_lsl'

if DEBUG_IPHONE in ["default", "verbatim"]:
    from pylsl import StreamInfo, StreamOutlet
    import liesl
    from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


# Type aliases
MESSAGE = Dict[str, Any]
PACKET_PAYLOAD = Union[MESSAGE, ByteString]
PACKET_CONTENTS = Tuple[PACKET_PAYLOAD, int, int, int]
CONFIG = Dict[str, Any]


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


def safe_socket_operation(func):  # This decorator detects errors and sends the IPhone object into an #ERROR state
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
    """
    A thread that listens for messages sent by the iPhone and processes them (e.g., updates state, notifies conditions.)
    """

    def __init__(self, *args):
        self._iphone: IPhone = args[0]
        self._running = True
        self.logger = logging.getLogger('session')
        threading.Thread.__init__(self)

    def run(self):
        self.logger.debug('iPhone: Entering Listening Loop')
        while self._running:
            try:
                payload, _, _, resp_tag = self._iphone._getpacket()
                self._iphone._process_received_message(payload, resp_tag)

                if resp_tag == 0:
                    debug_print(f"Listener received: {payload}")
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
    """
    Handles interactions with an iPhone device running the Neurobooth app.
    """

    # Constants for interfacing with the app
    TYPE_MESSAGE = 101
    VERSION = 1

    # State transition directed graph. States start with # and messages start with @.
    # The nested (key->value) structure is (#CURRENT_STATE->(@MESSAGE->#NEXT_STATE)), where if @MESSAGE is received in
    # #CURRENT_STATE, then the state machine should transition to #NEXT_STATE.
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
    MESSAGE_KEYS = {"MessageType", "SessionID", "TimeStamp", "Message"}

    @safe_socket_operation  # safe_socket decorator for self.sock.send
    def _socket_send(self, packet):
        return self.sock.send(packet)

    @safe_socket_operation  # safe_socket decorator for self.sock.recv
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
        self.streaming = False
        self.streamName = "IPhoneFrameIndex"
        self.outlet_id = str(uuid.uuid4())
        self.logger = logging.getLogger('session')

        # --------------------------------------------------------------------------------
        # Lock-based threading objects and their associated protected data
        # --------------------------------------------------------------------------------
        self._timeout_cond = 5  # Default threading timeout

        self._frame_preview_data = b""
        self._frame_preview_cond = Condition()

        self._dump_video_data = b""
        self._dump_video_cond = Condition()

        self._allmessages = []
        self._message_lock = RLock()

        self._state = "#DISCONNECTED"  # Entry point of state machine
        self._state_lock = RLock()

        self._latest_message = {}
        self._latest_message_type = ''
        self._wait_for_reply_cond = Condition()

        self.ready_event = Event()  # Used to check if we have re-entered the ready state by ensure_stopped()
        # --------------------------------------------------------------------------------

        self.logger.debug('iPhone: Created Object')

    def _validate_message(self, message: MESSAGE, tag: int) -> bool:
        """
        Validate the structure of a message and update the state machine if validated.

        Parameters
        ----------
        message
            The message to validate
        tag
            The associated message tag

        Returns
        -------
        success
            Whether the function call was successful.
        """
        if tag == 1:  # TAG==1 corresponds to PREVIEW file receiving
            msg_type = "@PREVIEWRECEIVE"
        elif tag == 2:  # TAG==2 corresponds to DUMP file receiving
            msg_type = "@DUMPRECEIVE"
        elif tag != 0:  # Incorrect / unexpected tag
            print(f"Incorrect tag received from IPhone. Tag={tag}")
            self.logger.error(f'iPhone: Incorrect tag ({tag}) received.')
            self.disconnect()
            return False
        else:  # Tag==0; all other messages
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

    def _update_state(self, msg_type: str) -> bool:
        """
        Update the state machine based on the given message type.

        Parameters
        ----------
        msg_type
            The message type string (e.g., @START) used to update the state machine.

        Returns
        -------
        success
            Whether the state update was successful. False if an invalid transition was requested.

        """
        with self._state_lock:
            debug_print(f"Initial State: {self._state}")
            allowed_trans = self.STATE_TRANSITIONS[self._state]
            if msg_type not in allowed_trans:
                print(f"Message {msg_type} is not valid in the state {self._state}.")
                self.logger.error(f"iPhone: Message {msg_type} is not valid in the state {self._state}.")
                self.disconnect()
                return False

            prev_state = self._state
            self._state = allowed_trans[msg_type]
            if self._state == '#ERROR':
                self.logger.error(f'iPhone: Entered #ERROR state from {prev_state} via {msg_type}!')
            elif self._state == '#READY':
                self.ready_event.set()
            debug_print(f"Outcome State:{self._state}")
        return True

    def _message(self, msg_type: str, timestamp: str = "", msg: str = "") -> MESSAGE:
        """
        Create a message given a subset of its contents (defaulting the rest).

        Parameters
        ----------
        msg_type
            The message type string (e.g., @START)
        timestamp
            The message timestamp
        msg
            The message contents

        Returns
        -------
        message
            A populated message dictionary.
        """
        if msg_type not in self.MESSAGE_TYPES:
            self.logger.error(f'iPhone [state={self._state}]: "{msg_type}" is not an allowed message')
            raise IPhoneError(f'Message type "{msg_type}" not in allowed message type list')
        return {
            "MessageType": msg_type,
            "SessionID": self.iphone_sessionID,
            "TimeStamp": timestamp,
            "Message": msg,
        }

    @staticmethod
    def _json_wrap(message: MESSAGE) -> str:
        """Convert a message dictionary into a JSON string for transmission."""
        return "####" + json.dumps(message)

    @staticmethod
    def _json_unwrap(payload: Union[str, bytes]) -> MESSAGE:
        """Convert a transmitted JSON string into a message dictionary."""
        return json.loads(payload[4:])

    def _update_message_log(self, msg: MESSAGE, tag: int) -> None:
        """Safely update the log of messages sent and received."""
        with self._message_lock:
            self._allmessages.append({"message": msg, "ctr_timestamp": str(datetime.now()), "tag": tag})

    def _sendpacket(self, msg_type: str, msg_contents: Optional[MESSAGE] = None) -> bool:
        """
        Validate a message, update the state machine, and send the message to the iPhone.

        Parameters
        ----------
        msg_type
            The message type string (e.g., @START)
        msg_contents
            Any non-default message entries/contents
        Returns
        -------
        success
            Whether the message was successfully validated and sent.
        """
        msg = self._message(msg_type)  # Default message contents
        if msg_contents is not None:  # Replace default contents with information from provided dict
            msg.update(msg_contents)

        if not self._validate_message(msg, 0):  # State transition is side effect of validate_message
            print(f"Message {msg} did not pass validation. Exiting _sendpacket.")
            self.logger.error(f'iPhone [state={self._state}]: Packet Validation Error: {msg}')
            self.disconnect()
            return False

        self._update_message_log(msg, self.tag)
        payload = IPhone._json_wrap(msg).encode("utf-8")
        payload_size = len(payload)
        packet = (
            struct.pack("!IIII", self.VERSION, self.TYPE_MESSAGE, self.tag, payload_size) + payload
        )
        self._socket_send(packet)
        return True

    def _send_and_wait_for_response(
            self,
            msg_type: str,
            msg_contents: Optional[MESSAGE] = None,
            wait_on: Optional[List[str]] = None,
    ) -> bool:
        """
        A convenience wrapper for _sendpacket that waits for a response (with tag==0) from the iPhone.
        The data of the response is NOT returned. If safe access to the message itself is required, then the calling
        function should instead do its own handling of an appropriate condition variable.

        Parameters
        ----------
        msg_type
            The message type string (e.g., @START) to be passed to _sendpacket
        msg_contents
            Any non-default message entries/contents to be passed to _sendpacket
        wait_on
            If None, wait for any response from the iPhone.
            If a list of message types is provided, wait for any of the specified message types.

        Returns
        -------
        success
            Whether the message was successfully validated and sent. A False value may also indicate a wait timeout.
        """
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

    @staticmethod
    def recvall(sock: socket.socket, n: int) -> ByteString:
        """
        Helper function to receive large packets.

        Parameters
        ----------
        sock
            The socket to pull from.
        n
            The number of bytes to retrieve.

        Returns
        -------
        data
            The data pulled from the socket.
        """
        MAX_RECV = (1 << 17) - 80  # Largest chunk of data to pull from the socket in any one call.

        fragments = []
        bytes_received = 0
        while True:
            bytes_to_pull = n - bytes_received
            if bytes_to_pull > MAX_RECV:
                bytes_to_pull = MAX_RECV

            packet = sock.recv(bytes_to_pull)
            bytes_received += len(packet)
            fragments.append(packet)

            if bytes_received >= n:
                break

        return b"".join(fragments)

    def _getpacket(self, timeout_sec: int = 20) -> PACKET_CONTENTS:
        """
        Retrieve a packet of data from the iPhone. This method will block until timed out.

        Parameters
        ----------
        timeout_sec
            How long to block before timing out

        Returns
        -------
        package_contents
            (payload, version, type, tag): Payload is either a message dictionary (tag == 0) or byte string
            (tag == 1 or tag == 2).
        """
        ready, _, _ = select.select([self.sock], [], [], timeout_sec)
        if not ready:
            self.logger.error(f"iPhone [state={self._state}]: Exceeded timeout for packet receipt")
            raise IPhoneError(
                f"Timeout for packet receive exceeded ({timeout_sec} sec)"
            )

        first_frame = self.sock.recv(16)
        version, type_, tag, payload_size = struct.unpack("!IIII", first_frame)

        if tag == 1 or tag == 2:
            self._validate_message({}, tag)
            payload = IPhone.recvall(self.sock, payload_size)
            return payload, version, type_, tag

        payload = self.sock.recv(payload_size)
        msg = IPhone._json_unwrap(payload)
        self._validate_message(msg, tag)
        return msg, version, type_, tag

    def _process_received_message(self, msg: PACKET_PAYLOAD, tag: int) -> None:
        """
        Notify appropriate conditions of message arrival.
        Also push data to LSL for appropriate messages.

        Parameters
        ----------
        msg
            The payload received from the iPhone. (Either a message or raw data depending on the tag.)
        tag
            The message tag that indicates how to handle the payload.
        """
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

                # Push data to LSL in an appropriate message was received
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

                self._wait_for_reply_cond.notify()

    @debug_lsl
    def lsl_push_sample(self, *args):
        self.outlet.push_sample(*args)

    @debug_lsl
    def lsl_print(self, *args):
        print(*args)

    def prepare(self, mock: bool = False, config: Optional[CONFIG] = None) -> bool:
        """
        Connect to the iPhone and open an LSL outlet.

        Parameters
        ----------
        mock
            Whether to use a mock iPhone
        config
            iPhone configuation options

        Returns
        -------
        success
            Whether the connection was successful
        """
        if mock:
            HOST = "127.0.0.1"  # Symbolic name meaning the local host
            PORT = 50009  # Arbitrary non-privileged port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            self._mock_handshake()
            self.connected = True
            return self.connected

        if config is None:
            config = {
                "NOTIFYONFRAME": "1",
                "VIDEOQUALITY": "1920x1080",
                "USECAMERAFACING": "BACK",
                "FPS": "240",
                "BRIGHTNESS": "50",
                "LENSPOS": "0.7",
            }
        self.notifyonframe = int(config["NOTIFYONFRAME"])
        success = self.handshake(config)
        if success:
            self.outlet = self.create_outlet()
            self.streaming = True
        return success and self.connected

    def handshake(self, config: CONFIG) -> bool:
        """
        Establish a connection with the iPhone; helper for prepare.

        Parameters
        ----------
        config
            iPhone configuation options

        Returns
        -------
        success
            Whether the connection was successful
        """
        if self._state != "#DISCONNECTED":
            print("Handshake is only available when disconnected")
            self.logger.error(f'iPhone [state={self._state}]: Attempted handshake in inappropriate state.')
            return False

        self.usbmux = USBMux()
        if not self.usbmux.devices:
            self.usbmux.process(0.1)
        if len(self.usbmux.devices) != 1:
            self.logger.error(
                f'iPhone [state={self._state}]: Incorrect number of usbmux devices (N={len(self.usbmux.devices)}).'
            )
            return False

        self.device = self.usbmux.devices[0]
        try:
            self.sock = self.usbmux.connect(self.device, IPHONE_PORT)
        except Exception as e:
            self.logger.error(f'iPhone [state={self._state}]: Unable to connect; error={e}')
            return False
        self._state = "#CONNECTED"

        # As soon as we're connected, start the parallel listening thread.
        self._listen_thread = IPhoneListeningThread(self)
        self._listen_thread.start()
        # self.sock.setblocking(0)
        self.connected = True

        msg_camera_config = {"Message": json.dumps(config)}
        print(msg_camera_config)
        return self._send_and_wait_for_response(
            "@STANDBY",
            msg_contents=msg_camera_config,
            wait_on=list(self.STATE_TRANSITIONS['#STANDBY'].keys()),
        )

    def _mock_handshake(self) -> bool:
        self._validate_message(self._message('@STANDBY'), 0)
        self._validate_message(self._message('@READY'), 0)
        return True

    @debug_lsl
    def create_outlet(self) -> StreamOutlet:
        """Create an LSL outlet; helper for prepare."""
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

    def start_recording(self, filename: str) -> None:
        """Signal the iPhone to start recording using the given filename"""
        msg_filename = {"Message": filename}
        self.logger.debug(f'iPhone [state={self._state}]: Sending @START Message')
        self._send_and_wait_for_response(
            "@START",
            msg_contents=msg_filename,
            wait_on=list(self.STATE_TRANSITIONS['#START'].keys()),
        )

    def stop_recording(self) -> None:
        """Signal the iPhone to stop recording."""
        self.logger.debug(f'iPhone [state={self._state}]: Sending @STOP Message')
        self.ready_event.clear()  # Clear this event so that ensure_stopped() can wait on it
        self._send_and_wait_for_response(
            "@STOP",
            wait_on=["@STOPTIMESTAMP", "@DISCONNECT", "@ERROR"],
        )

    def frame_preview(self) -> ByteString:
        """Retrieve a frame preview from the iPhone,"""
        self.logger.debug(f'iPhone [state={self._state}]: Sending @PREVIEW Message')
        with self._frame_preview_cond:
            self._frame_preview_data = b""
            if self._sendpacket("@PREVIEW"):
                self._frame_preview_cond.wait(timeout=self._timeout_cond)
            return self._frame_preview_data

    def dumpall_getfilelist(self, log_files: bool = True) -> Optional[List[str]]:
        """
        Get a list of files saved on the iPhone.

        Parameters
        ----------
        log_files
            Whether to log the list of retrieved files using the session logger.

        Returns
        -------
        file_names
            The list of files saved on the iPhone.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMPALL Message')
        with self._wait_for_reply_cond:
            if not self._sendpacket("@DUMPALL"):
                return None

            if not self._wait_for_reply_cond.wait_for(
                lambda: self._latest_message_type in self.STATE_TRANSITIONS['#DUMPALL'].keys(),
                timeout=self._timeout_cond,
            ):
                self.logger.error('Timeout when waiting for @FILESTODUMP.')
                return None

            filelist = self._latest_message["Message"]
            if self._state == "#ERROR":
                self.logger.error(f'iPhone [state={self._state}]: @DUMPALL Error; message="{filelist}"')
                return None

            if log_files:
                self.logger.debug(f"iPhone [state={self._state}]: File List (N={len(filelist)}) = {filelist}")

            return filelist

    def dump(self, filename: str, timeout_sec=None) -> (bool, ByteString):
        """
        Retrieve a file from the iPhone.

        Parameters
        ----------
        filename
            The file (from the list returned by dumpall_getfilelist) to retrieve.
        timeout_sec
            Wait the specified amount of time for the file transfer to complete.

        Returns
        -------
        success
            False if a timeout occurred or the request could not be sent; a zero-byte file will be returned.
        """
        success = False
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMP Message')
        with self._dump_video_cond:
            self._dump_video_data = b""
            if self._sendpacket("@DUMP", msg_contents={"Message": filename}):
                success = self._dump_video_cond.wait(timeout=timeout_sec)
            return success, self._dump_video_data

    def dumpsuccess(self, filename: str) -> bool:
        """
        Notify the iPhone that it may delete the specified file.

        Parameters
        ----------
        filename
            The file (from the list returned by dumpall_getfilelist) to delete.

        Returns
        -------
        success
            Whether the @DUMPSUCCESS message was successfully sent.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMPSUCCESS Message')
        return self._sendpacket("@DUMPSUCCESS", msg_contents={"Message": filename})

    def start(self, filename: str) -> None:
        """Start data capture."""
        self.streaming = True
        filename += "_IPhone"
        filename = op.split(filename)[-1]
        self.lsl_print(f"-new_filename-:{self.streamName}:{filename}.mov")
        time.sleep(0.05)
        self.lsl_print(f"-new_filename-:{self.streamName}:{filename}.json")
        self.start_recording(filename)

    def stop(self) -> None:
        """Stop data capture."""
        self.stop_recording()
        self.streaming = False

    def ensure_stopped(self, timeout_seconds: float) -> None:
        """Check to make sure that we have transitioned from the #STOP state back to the #READY state."""
        success = self.ready_event.wait(timeout=timeout_seconds)
        if not success:
            self.logger.error(
                f'iPhone [state={self._state}]: Ready state not reached during stop sequence before timeout!'
            )
            raise IPhoneError('Ready state not reached during stop sequence before timeout!')

        self.logger.debug(f'iPhone [state={self._state}]: Transition to #READY Detected')

    def close(self) -> None:
        """Close the stream and disconnect the iPhone"""
        self.disconnect()

    def disconnect(self) -> bool:
        """Disconnect the iPhone"""
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


if __name__ == "__main__":
    import argparse

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
    parser.add_argument(
        '--log-console',
        action='store_true',
        help='Print session logs to the console.'
    )
    parser.add_argument(
        '--log-file',
        default=None,
        type=str,
        help='Write session logs to the specified file.',
    )
    args = parser.parse_args()

    if args.log_console or args.log_file is not None:
        from neurobooth_os.logging import make_session_logger_debug
        make_session_logger_debug(file=args.log_file, console=args.log_console)


    # Creating and starting mock streams:

    # config={'NOTIFYONFRAME':'1',
    #                        'VIDEOQUALITY':'3840x2160',
    #                        'USECAMERAFACING':'BACK','FPS':'60'}

    # config={'NOTIFYONFRAME':'1',
    #                        'VIDEOQUALITY':'1920x1080',
    #                        'USECAMERAFACING':'BACK','FPS':'120 or 240'}
    iphone = IPhone("iphone")
    default_config: CONFIG = {
        "NOTIFYONFRAME": "1",
        "VIDEOQUALITY": "1920x1080",
        "USECAMERAFACING": "BACK",
        "FPS": "240",
        "BRIGHTNESS": "50",
        "LENSPOS": "0.7",
    }

    if not iphone.prepare(config=default_config):
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
