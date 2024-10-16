import argparse
import os.path as op
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
from enum import IntEnum
from hashlib import md5
from base64 import b64decode

from neurobooth_os.iout.metadator import post_message, get_database_connection
from neurobooth_os.iout.stim_param_reader import DeviceArgs
from neurobooth_os.iout.usbmux import USBMux
from neurobooth_os.log_manager import APP_LOG_NAME
from neurobooth_os.msg.messages import NewVideoFile, Request, StatusMessage, DeviceInitialization

# --------------------------------------------------------------------------------
# Module-level constants and debugging flags
# --------------------------------------------------------------------------------
IPHONE_PORT: int = 2345  # IPhone should have socket on this port open if we're connecting to it.

DEBUG_LOGGING: bool = False  # If True, enable additional logging outputs. May slow down the script.
DISABLE_LSL: bool = False  # If True, LSL streams will not be created nor will received data be pushed.

if not DISABLE_LSL:  # Conditional imports based on flags
    from pylsl import StreamInfo, StreamOutlet
    import liesl
    from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description


# --------------------------------------------------------------------------------
# Type aliases
# --------------------------------------------------------------------------------
MESSAGE = Dict[str, Any]
PACKET_PAYLOAD = Union[MESSAGE, ByteString]
PACKET_CONTENTS = Tuple[PACKET_PAYLOAD, int, int, int]
CONFIG = Dict[str, Any]


class MessageTag(IntEnum):
    """Packets/messages sent by the iPhone are accompanied by a integer tag denoting the type of contents."""
    NORMAL_MESSAGE = 0
    FRAME_PREVIEW = 1
    DUMP_FILE = 2
    DUMP_FILE_CHUNK = 3
    DUMP_LAST_FILE_CHUNK = 4


# --------------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------------
class IPhoneError(Exception):
    """Base class for iPhone-related errors."""
    pass


class IPhonePanic(IPhoneError):
    """An exception to signal code should panic and disconnect if a serious error is encountered."""
    pass


class IPhoneTimeout(IPhoneError):
    """Signals that waiting on a particular response or threading condition failed."""
    pass


class IPhoneHashMismatch(IPhoneError):
    """Signals that a transferred file does not have the expected hash"""
    pass


# --------------------------------------------------------------------------------
# Hardware Interface Code
# --------------------------------------------------------------------------------
def _handle_panic(func):
    """Decorator to wrap a function call in a try/except to detect panic and generically handle panic exceptions."""
    @functools.wraps(func)
    def wrapper_panic(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IPhonePanic as e:
            _iphone: IPhone = args[0]
            _iphone.panic(e)
            return None
    return wrapper_panic


class IPhone:
    """
    Handles interactions with an iPhone device running the Neurobooth app.
    Intended Lifecycle:
     1. Create object.
     2. prepare() to connect to iPhone and initialize LSL stream.
     3. Record data: start() -> stop() -> ensure_stopped(). Repeat cycle as needed.
     4. close() to disconnect the iPhone.
    At any point during the lifecycle a panic may occur if an error is encountered. This will disconnect the iPhone.
    """

    # Constants for interfacing with the app
    TYPE_MESSAGE = 101
    VERSION = 1

    # State transition directed graph. States start with # and messages start with @.
    # The nested (key->value) structure is (#CURRENT_STATE->(@MESSAGE->#NEXT_STATE)), where if @MESSAGE is received in
    # #CURRENT_STATE, then the state machine should transition to #NEXT_STATE.
    STATE_TRANSITIONS = {
        "#DISCONNECTED": {
            "@HANDSHAKE": "#CONNECTED",
            "@ERROR": "#ERROR",
        },
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
            "@CHUNKRECEIVE": "#DUMPCHUNK",
            "@LASTCHUNKRECEIVE": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
        "#DUMPCHUNK": {
            "@CHUNKRECEIVE": "#DUMPCHUNK",
            "@LASTCHUNKRECEIVE": "#READY",
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
            "@INPROGRESSTIMESTAMP": "#READY",
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
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
        "#ERROR": {
            "@DISCONNECT": "#DISCONNECTED",
            "@ERROR": "#ERROR",
        },
    }
    MESSAGE_TYPES = []
    for elem in STATE_TRANSITIONS:
        MESSAGE_TYPES += STATE_TRANSITIONS[elem].keys()
    MESSAGE_TYPES = set(MESSAGE_TYPES)
    MESSAGE_KEYS = {"MessageType", "SessionID", "TimeStamp", "Message"}

    def __init__(self, name, sess_id="", mock=False, device_args: DeviceArgs = None, enable_timeout_exceptions=False):
        self.connected = False
        self.tag = 0
        self.iphone_sessionID = sess_id
        self.name = name
        self.mock = mock
        if not DISABLE_LSL:  # Device and sensor IDs are only needed if streaming data to LSL.
            self.device_id = device_args.device_id
            self.sensor_ids = device_args.sensor_ids
        self.enable_timeout_exceptions = enable_timeout_exceptions
        self.streaming = False
        self.streamName = "IPhoneFrameIndex"
        self.outlet_id = str(uuid.uuid4())
        self.logger = logging.getLogger(APP_LOG_NAME)

        # --------------------------------------------------------------------------------
        # Lock-based threading objects and their associated protected data
        # --------------------------------------------------------------------------------
        self._default_timeout_sec = 5
        self._dumpall_timeout_sec = 120  # @DUMPALL can take a while since it computes MD5 hashes

        self._state = "#DISCONNECTED"  # Entry point of state machine
        self._state_lock = RLock()

        self._frame_preview_data = b""
        self._frame_preview_cond = Condition()

        self._dump_video_data = b""
        self._dump_video_cond = Condition()

        self._latest_message = {}
        self._latest_message_type = ''
        self._wait_for_reply_cond = Condition()

        self.ready_event = Event()  # Used to check if we have re-entered the ready state by ensure_stopped()
        # --------------------------------------------------------------------------------

        self.logger.debug('iPhone: Created Object')

    def panic(self, e: IPhonePanic, disconnect: bool = True) -> None:
        """
        Respond to an IPhonePanic being raised. Log errors, go to error state, and (optionally) disconnect.

        :param e: The raised IPhonePanic exception.
        :param disconnect: Whether to trigger a disconnect as a result of the panic.
        """
        self.logger.exception(f'iPhone [state={self._state}]: PANIC Message: {e}')
        with get_database_connection() as conn:
            IPhone.send_status_msg(f'iPhone PANIC (Please restart iphone app and session): {e}', conn)

        with self._state_lock:
            self._state = "#ERROR"

        if disconnect:
            self.disconnect()

    def _raise_timeout(self, event_name: str) -> None:
        """
        Raise an IPhoneTimeout if not disabled.

        :param event_name: The name of the message/condition that timed out. (Used for logging.)
        """
        self.logger.error(
            f'iPhone [state={self._state}]: Timeout encountered when waiting for response to {event_name}.'
        )
        if self.enable_timeout_exceptions:
            raise IPhoneTimeout(f'Timeout when waiting for {event_name}.')

    def _update_state(self, msg_type: str) -> None:
        """
        Update the state machine based on the given message type.

        :param msg_type: The message type string (e.g., @START) used to update the state machine.
        """
        with self._state_lock:
            if DEBUG_LOGGING:
                self.logger.debug(f"Initial State: {self._state}")

            # Check that the requested transition is valid
            allowed_trans = self.STATE_TRANSITIONS[self._state]
            if msg_type not in allowed_trans:
                self.logger.error('iPhone: PANIC')
                raise IPhonePanic(f'Message {msg_type} is not valid in the current state.')

            # Perform the transition
            prev_state = self._state
            self._state = allowed_trans[msg_type]

            # Special handling for certain states
            if self._state == '#ERROR':
                self.logger.error(f'iPhone: Entered #ERROR state from {prev_state} via {msg_type}!')
            elif self._state == '#READY':
                self.ready_event.set()

            if DEBUG_LOGGING:
                self.logger.debug(f"Outcome State: {self._state}")

    def _message(self, msg_type: str, timestamp: str = "", msg: str = "") -> MESSAGE:
        """
        Create a message given a subset of its contents (defaulting the rest).

        :param msg_type: The message type string (e.g., @START)
        :param timestamp: The message timestamp
        :param msg: The message contents
        :returns: A populated message dictionary.
        """
        if msg_type not in self.MESSAGE_TYPES:
            self.logger.error('iPhone: PANIC')
            raise IPhonePanic(f'Message type "{msg_type}" not in allowed message type list.')

        return {
            "MessageType": msg_type,
            "SessionID": self.iphone_sessionID,
            "TimeStamp": timestamp,
            "Message": msg,
        }

    def _validate_message(self, message: MESSAGE) -> None:
        """
        Validate the structure of a message. Panic if an error is detected.

        :param message: The message to validate
        """
        if len(message) != len(self.MESSAGE_KEYS):
            self.logger.error('iPhone: PANIC')
            raise IPhonePanic(f'Message has incorrect length: {message}')

        for key in message:
            if key not in self.MESSAGE_KEYS:
                self.logger.error('iPhone: PANIC')
                raise IPhonePanic(f'Message has incorrect key: key={key}; message={message}')

    @staticmethod
    def _json_wrap(message: MESSAGE) -> str:
        """Convert a message dictionary into a JSON string for transmission."""
        return "####" + json.dumps(message)

    @staticmethod
    def _json_unwrap(payload: Union[str, bytes]) -> MESSAGE:
        """Convert a transmitted JSON string into a message dictionary."""
        return json.loads(payload[4:])

    def _send_packet(self, msg_type: str, msg_contents: Optional[MESSAGE] = None) -> None:
        """
        Create and validate a message, update the state machine, and send the message to the iPhone.

        :param msg_type: The message type string (e.g., @START)
        :param msg_contents: Any non-default message entries/contents
        """
        msg = self._message(msg_type)  # Default message contents
        if msg_contents is not None:  # Replace default contents with information from provided dict
            msg.update(msg_contents)
        self._validate_message(msg)

        self._update_state(msg_type)

        payload = IPhone._json_wrap(msg).encode("utf-8")
        payload_size = len(payload)
        packet = (
            struct.pack("!IIII", self.VERSION, self.TYPE_MESSAGE, self.tag, payload_size) + payload
        )

        try:
            self.sock.send(packet)
        except Exception as e:
            self.logger.error(f'iPhone: PANIC: {e}')
            raise IPhonePanic(f'Error occurred sending signal through the socket') from e

    def _send_and_wait_for_response(
            self,
            msg_type: str,
            msg_contents: Optional[MESSAGE] = None,
            wait_on: Optional[List[str]] = None,
    ) -> None:
        """
        A convenience wrapper for _send_packet that waits for a response (with tag==0) from the iPhone.
        The data of the response is NOT returned. If safe access to the message itself is required, then the calling
        function should instead do its own handling of an appropriate condition variable.

        :param msg_type: The message type string (e.g., @START) to be passed to _send_packet
        :param msg_contents: Any non-default message entries/contents to be passed to _send_packet
        :param wait_on: If None, wait for any response from the iPhone.
            If a list of message types is provided, wait for any of the specified message types.
        """
        with self._wait_for_reply_cond:
            self._send_packet(msg_type, msg_contents=msg_contents)

            if wait_on is None:
                success = self._wait_for_reply_cond.wait(timeout=self._default_timeout_sec)
            else:
                success = self._wait_for_reply_cond.wait_for(
                        lambda: self._latest_message_type in wait_on,
                        timeout=self._default_timeout_sec,
                )

            if not success:
                self._raise_timeout(msg_type)

    def listen(self):
        """Called by the listener thread. Attempt to receive and process a message."""
        payload, _, _, resp_tag = self._get_packet()

        if DEBUG_LOGGING:
            debug_msg = payload if resp_tag == MessageTag.NORMAL_MESSAGE else f'Tag {resp_tag}'
            self.logger.debug(f'Listener Received: {debug_msg}')

        self._process_received_message(payload, resp_tag)

    @staticmethod
    def recvall(sock: socket.socket, n: int) -> ByteString:
        """
        Helper function to receive large packets.

        :param sock: The socket to pull from.
        :param n: The number of bytes to retrieve.
        :returns: The data pulled from the socket.
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

    def _get_packet(self, timeout_sec: int = 20) -> PACKET_CONTENTS:
        """
        Retrieve a packet of data from the iPhone. This method will block until timed out.

        :param timeout_sec: How long to block before timing out
        :returns: (payload, version, type, tag): Payload is either a message dictionary (tag == 0) or byte string
            (tag == 1 or tag == 2).
        """
        ready, _, _ = select.select([self.sock], [], [], timeout_sec)
        if not ready:
            raise IPhoneTimeout(f"Timeout for packet receive exceeded ({timeout_sec} sec)")

        first_frame = self.sock.recv(16)
        version, type_, tag, payload_size = struct.unpack("!IIII", first_frame)

        if tag in (
                MessageTag.FRAME_PREVIEW,
                MessageTag.DUMP_FILE,
                MessageTag.DUMP_FILE_CHUNK,
                MessageTag.DUMP_LAST_FILE_CHUNK
        ):
            payload = IPhone.recvall(self.sock, payload_size)
            return payload, version, type_, tag
        elif tag == MessageTag.NORMAL_MESSAGE:
            payload = self.sock.recv(payload_size)
            msg = IPhone._json_unwrap(payload)
            self._validate_message(msg)
            return msg, version, type_, tag
        else:
            self.logger.error('iPhone: PANIC')
            raise IPhonePanic(f'Incorrect tag ({tag}) received.')

    def _process_received_message(self, msg: PACKET_PAYLOAD, tag: int) -> None:
        """
        Push to LSL (if appropriate), update the state machine, and notify appropriate conditions of message arrival.

        :param msg: The payload received from the iPhone. (Either a message or raw data depending on the tag.)
        :param tag: The message tag that indicates how to handle the payload.
        """
        if tag == MessageTag.FRAME_PREVIEW:
            self._update_state("@PREVIEWRECEIVE")
            with self._frame_preview_cond:
                self._frame_preview_data = msg
                self._frame_preview_cond.notify()
        elif tag == MessageTag.DUMP_FILE:
            self._update_state("@DUMPRECEIVE")
            with self._dump_video_cond:
                self._dump_video_data = msg
                self._dump_video_cond.notify()
        elif tag == MessageTag.DUMP_FILE_CHUNK:
            self._update_state("@CHUNKRECEIVE")
            self.logger.debug(f'iPhone: Received File Chunk ({len(msg)/(1<<20):0.1f} MiB)')
            with self._dump_video_cond:
                self._dump_video_data += msg
        elif tag == MessageTag.DUMP_LAST_FILE_CHUNK:
            self._update_state("@LASTCHUNKRECEIVE")
            self.logger.debug(f'iPhone: Received Last File Chunk ({len(msg) / (1 << 20):0.1f} MiB)')
            with self._dump_video_cond:
                self._dump_video_data += msg
                self._dump_video_cond.notify()
        else:
            self._lsl_push_sample(msg)  # Push before trying to acquire locks to ensure accurate timing

            message_type = msg["MessageType"]
            if message_type == '@ERROR':
                self.logger.error(f'iPhone: Error received from phone: {msg["Message"]}')
            self._update_state(message_type)

            with self._wait_for_reply_cond:
                self._latest_message = msg
                self._latest_message_type = message_type
                self._wait_for_reply_cond.notify()

    def _lsl_push_sample(self, message: MESSAGE) -> None:
        """
        Push a sample to LSL if an appropriate message type and LSL is enabled.
        :param message: The message to parse and possibly push to LSL.
        """
        # Guards to ensure that we only try to push data where appropriate
        if DISABLE_LSL or message["MessageType"] not in ("@STARTTIMESTAMP", "@INPROGRESSTIMESTAMP", "@STOPTIMESTAMP",):
            return

        # Parse data from message
        frame_info = eval(message["TimeStamp"])  # Nasty trick to turn the message string into an object
        frame_num, frame_time = int(frame_info["FrameNumber"]), float(frame_info["Timestamp"])

        # Push the sample
        lsl_sample = [frame_num, frame_time, time.time()]
        self.outlet.push_sample(lsl_sample)

        if DEBUG_LOGGING:
            self.logger.debug(f'LSL Push: {lsl_sample}')

    def prepare(self, mock: bool = False, config: Optional[CONFIG] = None) -> bool:
        """
        Called during a PREPARE message to the server (i.e., "Connect Devices").
        Connects to the iPhone and opens an LSL outlet.

        :param mock: Whether to use a mock iPhone
        :param config: iPhone configuation options
        :returns: Whether the connection was successful
        """
        if mock:
            return self._mock_handshake() and self.connected

        if config is None:
            config = {
                "NOTIFYONFRAME": "1",
                "VIDEOQUALITY": "1920x1080",
                "USECAMERAFACING": "BACK",
                "FPS": "240",
                "BRIGHTNESS": "50",
                "LENSPOS": "0.7",
            }

        success = self._handshake(config)
        if success and not DISABLE_LSL:
            self.outlet = self._create_outlet()
            self.streaming = True
        return success and self.connected

    def _handshake(self, config: CONFIG) -> bool:
        """
        Establish a connection with the iPhone; helper for prepare.

        :param config: iPhone configuation options
        :returns: Whether the connection was successful
        """
        if self._state != "#DISCONNECTED":
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
            self._update_state('@HANDSHAKE')
        except Exception as e:
            self.logger.error(f'iPhone [state={self._state}]: Unable to connect; error={e}')
            return False

        # As soon as we're connected, start the parallel listening thread.
        self._listen_thread = IPhoneListeningThread(self)
        self._listen_thread.start()
        # self.sock.setblocking(0)
        self.connected = True

        # Send the configuration to the iPhone and wait for a response
        msg_camera_config = {"Message": json.dumps(config)}
        try:
            self._send_and_wait_for_response(
                "@STANDBY",
                msg_contents=msg_camera_config,
                wait_on=list(self.STATE_TRANSITIONS['#STANDBY'].keys()),
            )
            return True
        except IPhonePanic as e:
            self.panic(e)
            return False

    def _mock_handshake(self) -> bool:
        try:
            HOST = "127.0.0.1"  # Symbolic name meaning the local host
            PORT = 50009  # Arbitrary non-privileged port
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((HOST, PORT))
            self.connected = True

            self._update_state('@HANDSHAKE')
            self._update_state('@STANDBY')
            self._update_state('@READY')
            return True
        except IPhonePanic as e:
            self.panic(e)
            return False
        except Exception as e:
            self.logger.error(f'iPhone [state={self._state}]: Unable to connect; error={e}')
            return False

    def _create_outlet(self) -> StreamOutlet:
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
            data_version=DataVersion(1, 1),
            columns=['FrameNum', 'Time_iPhone', 'Time_ACQ'],
            column_desc={
                'FrameNum': 'App-tracked frame number',
                'Time_iPhone': 'App timestamp (s)',
                'Time_ACQ': 'Local machine timestamp (s)',
            }
        )
        body = DeviceInitialization(stream_name=self.streamName, outlet_id=self.outlet_id)
        msg = Request(source="IPhone", destination="CTR", body=body)
        with get_database_connection() as conn:
            post_message(msg, conn)

        return StreamOutlet(info)

    @_handle_panic
    def _start_recording(self, filename: str) -> None:
        """
        Signal the iPhone to start recording.

        :param filename: The file name root (i.e., no extension) to be passed to the iPhone.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @START Message')
        self._send_and_wait_for_response(
            "@START",
            msg_contents={"Message": filename},
            wait_on=list(self.STATE_TRANSITIONS['#START'].keys()),
        )

    @_handle_panic
    def _stop_recording(self) -> None:
        """Signal the iPhone to stop recording."""
        self.logger.debug(f'iPhone [state={self._state}]: Sending @STOP Message')
        self.ready_event.clear()  # Clear this event so that ensure_stopped() can wait on it
        self._send_and_wait_for_response(
            "@STOP",
            wait_on=["@STOPTIMESTAMP", "@DISCONNECT", "@ERROR"],
        )

    def frame_preview(self) -> ByteString:
        """
        Retrieve a frame preview from the iPhone.

        :returns: The raw data of the image, or an empty byte string if the condition times out.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @PREVIEW Message')
        with self._frame_preview_cond:
            self._frame_preview_data = b""
            try:
                self._send_packet("@PREVIEW")
                if not self._frame_preview_cond.wait(timeout=self._default_timeout_sec):
                    self._raise_timeout("@PREVIEW")
            except IPhonePanic as e:
                self.panic(e)
            return self._frame_preview_data

    @_handle_panic
    def dumpall_getfilelist(self) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        """
        Fetch a list of files saved on the iPhone.

        :returns: The list of names and hashes of files saved on the iPhone, or None if the condition times out.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMPALL Message')
        with self._wait_for_reply_cond:
            self._send_packet("@DUMPALL")

            if not self._wait_for_reply_cond.wait_for(
                lambda: self._latest_message_type in self.STATE_TRANSITIONS['#DUMPALL'].keys(),
                timeout=self._dumpall_timeout_sec,
            ):
                self._raise_timeout("@DUMPALL")
                return None, None

            if self._state == '#ERROR':  # Usually occurs when no files present
                self.logger.error(f'iPhone [state={self._state}]: {self._latest_message["Message"]}')
                return None, None

            file_info = self._latest_message["Message"]
            file_names = [info['file'] for info in file_info]
            file_hashes = [info['md5'] for info in file_info]
            if DEBUG_LOGGING:
                self.logger.debug(f"iPhone [state={self._state}]: File List (N={len(file_info)}) = {file_names}")
            return file_names, file_hashes

    def dump(
            self,
            filename: str,
            expected_hash: str,
            timeout_sec: Optional[float] = None,
    ) -> (bool, ByteString):
        """
        Retrieve a file from the iPhone.

        :param filename: The file (from the list returned by dumpall_getfilelist) to retrieve.
        :param expected_hash: Verify the transferred data using an MD5 (base64 encoded) hash.
        :param timeout_sec: Wait the specified amount of time for the file transfer to complete. No timeout if None.
        :returns: The raw data returned from the phone, or zero bytes if timed out.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMP Message')
        with self._dump_video_cond:
            self._dump_video_data = b""  # Clean slate is necessary for file chunk receipt logic
            try:
                self._send_packet("@DUMP", msg_contents={"Message": filename})
                if not self._dump_video_cond.wait(timeout=timeout_sec):
                    self._raise_timeout("@DUMP")
            except IPhonePanic as e:
                self.panic(e)

            # Compute/transform Hashes
            self.logger.debug(f'iPhone [state={self._state}]: Computing Hashes')
            iphone_hash = b64decode(expected_hash).hex()  # Transform base64 encoded string to hex encoding
            local_hash = md5(self._dump_video_data).hexdigest()
            self.logger.debug(f'iPhone [state={self._state}]: iphone_hash={iphone_hash}; local_hash={local_hash}')

            if iphone_hash != local_hash:  # Compare hashes
                self.logger.warning(f'Received file ({filename}) does not match given hash.')
                raise IPhoneHashMismatch(f'Received file ({filename}) does not match given hash.')

            return self._dump_video_data

    @_handle_panic
    def dump_success(self, filename: str) -> None:
        """
        Notify the iPhone that it may delete the specified file.

        :param filename: The file (from the list returned by dumpall_getfilelist) to delete.
        """
        self.logger.debug(f'iPhone [state={self._state}]: Sending @DUMPSUCCESS Message')
        self._send_packet("@DUMPSUCCESS", msg_contents={"Message": filename})

    def start(self, filename: str) -> None:
        """
        Called during a START message to the server. Start data capture.

        :param filename: The task file name supplied by the server.
        """
        self.streaming = True
        filename += "_IPhone"
        filename = op.split(filename)[-1]
        if not DISABLE_LSL:
            with get_database_connection() as conn:
                IPhone.send_file_msg(self.streamName, f"{filename}.mov", conn)
                time.sleep(0.05)
                IPhone.send_file_msg(self.streamName, f"{filename}.json", conn)
        self._start_recording(filename)

    @staticmethod
    def send_file_msg(stream_name, file_name, conn):
        body = NewVideoFile(event="-new_filename-", stream_name=stream_name, filename=f"{file_name}")
        msg = Request(source="IPhone", destination="CTR", body=body)
        post_message(msg, conn)

    @staticmethod
    def send_status_msg(txt, conn):
        body = StatusMessage(text=txt)
        msg = Request(source="IPhone", destination="CTR", body=body)
        post_message(msg, conn)

    def stop(self) -> None:
        """Called during a START message to the server. Stop data capture."""
        self._stop_recording()
        self.streaming = False

    @_handle_panic
    def ensure_stopped(self, timeout_seconds: float) -> None:
        """
        Check to make sure that we have transitioned from the #STOP state back to the #READY state.

        :param timeout_seconds: How long to wait for the transition back to #READY before a panic is triggered.
        """
        success = self.ready_event.wait(timeout=timeout_seconds)
        if not success:
            self.logger.error('iPhone: PANIC')
            raise IPhonePanic('Ready state not reached during stop sequence before timeout!')

        self.logger.debug(f'iPhone [state={self._state}]: Transition to #READY Detected')

    def close(self) -> None:
        """Called during a CLOSE or SHUTDOWN message to the server. Disconnect the iPhone"""
        self.disconnect()

    def disconnect(self, join_listener: bool = True) -> bool:
        """
        Disconnect the iPhone

        :param join_listener: Should be set to False if called from the listener thread, otherwise True.
        """
        if self._state == "#DISCONNECTED":
            self.logger.debug("IPhone device is already disconnected")
            return False

        # Send disconnect signal
        self.logger.debug(f'iPhone [state={self._state}]: Disconnecting')
        self._update_state("@DISCONNECT")

        time.sleep(4)  # Give things some time to happen; was here before rewrite, but why?

        # Try to stop the listener thread
        self._listen_thread.stop()
        self.sock.close()  # Closing the socket will force an error that will break the thread out of its wait
        if join_listener:
            self._listen_thread.join(timeout=3)
            if self._listen_thread.is_alive():
                self.logger.error(f'iPhone [state={self._state}]: Could not stop listening thread.')
                raise IPhoneError("Cannot stop the recording thread")

        self.connected = False
        self.streaming = False
        return True


class IPhoneListeningThread(threading.Thread):
    """
    A thread that listens for messages sent by the iPhone and processes them (e.g., updates state, notifies conditions.)
    """
    def __init__(self, iphone: IPhone):
        self._iphone = iphone
        self._running = True
        self.logger = logging.getLogger(APP_LOG_NAME)
        threading.Thread.__init__(self)

    def run(self):
        try:
            self.logger.debug('iPhone: Started Listening Thread')
            while self._running:
                self.listen()
        except IPhonePanic as e:  # Top-level exceptions that will kill the loop
            self._iphone.panic(e, disconnect=False)
            self._iphone.disconnect(join_listener=False)
        finally:
            self.logger.debug('iPhone: Exiting Listening Thread')

    def listen(self):
        """Call the iPhone listen() method and sort through various possible exceptions."""
        try:
            self._iphone.listen()
        except IPhoneTimeout as e:  # These occur normally; only log if the module debug flag is set
            if DEBUG_LOGGING:
                self.logger.debug(f"iPhone: {e}")
        except struct.error as e:  # Can occur if the app is on too long and iPhone blocks the port
            raise IPhonePanic('Communications Breakdown') from e
        except OSError as e:
            if not self._running:
                return  # OSError occurs when the socket is closed during shutdown; do nothing if thread is stopped
            if 'WinError 10053' in str(e):  # Can occur if the app is on too long and iPhone blocks the port
                raise IPhonePanic('Communications Breakdown') from e
            # Simply log anything unexpected
            self.logger.error(f'iPhone: Listening loop encountered an error: {e}')
        except Exception as e:  # Simply log any other unexpected errors
            self.logger.error(f'iPhone: Listening loop encountered an error: {e}')

    def stop(self):
        self._running = False


# --------------------------------------------------------------------------------
# Testing Script
# --------------------------------------------------------------------------------
def test_script():
    args = script_parse_args()
    script_capture_data(args.subject_id, args.recording_folder, args.duration)
    script_results(args.recording_folder, args.subject_id, args.show_plots)


def script_parse_args() -> argparse.Namespace:
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
        from neurobooth_os.log_manager import make_session_logger_debug
        make_session_logger_debug(file=args.log_file, console=args.log_console)

    return args


def script_capture_data(subject_id: str, recording_folder: str, capture_duration: int) -> None:
    dev_args = DeviceArgs(
        ENV_devices={'IPhone_dev_1': {}},
        device_id='IPhone_dev_1',
        device_name='IPhone',
        wearable_bool=False,
        sensor_ids=['IPhone_sens_1'],
        sensor_array=[],  # The sensor array and arg parser are not needed by the test script
        arg_parser='',
    )

    iphone = IPhone("IPhone", device_args=dev_args)
    default_config: CONFIG = {
        "NOTIFYONFRAME": "1",
        "VIDEOQUALITY": "1920x1080",
        "USECAMERAFACING": "BACK",
        "FPS": "240",
        "BRIGHTNESS": "50",
        "LENSPOS": "0.7",
    }

    if not iphone.prepare(config=default_config):
        with get_database_connection() as conn:
            IPhone.send_status_msg("Could not connect to iphone", conn)
    iphone.frame_preview()

    # Start LSL
    if not DISABLE_LSL:
        streamargs = {"name": "IPhoneFrameIndex"}
        session = liesl.Session(prefix=subject_id, streamargs=[streamargs], mainfolder=recording_folder)
        session.start_recording()

    # Data capture
    iphone.start(f'{subject_id}_{datetime.now().strftime("%Y-%m-%d_%Hh-%Mm-%Ss")}_task_obs_1')
    time.sleep(capture_duration)
    iphone.stop()

    # Stop LSL
    if not DISABLE_LSL:
        session.stop_recording()

    iphone.disconnect()


def script_results(recording_folder: str, subject_id: str, show_plots: bool) -> None:
    import pyxdf
    import glob
    import numpy as np

    path = op.join(recording_folder, subject_id, 'recording_R0*.xdf')
    fname = glob.glob(path)[-1]
    data, header = pyxdf.load_xdf(fname)

    ts = data[0]["time_series"]
    ts_pc = [t[1] for t in ts]
    ts_ip = [t[2] for t in ts]

    df_pc = np.diff(ts_pc)
    df_ip = np.diff(ts_ip)
    print(f"mean diff diff: {np.mean(np.abs(df_pc[1:] - df_ip[1:])) * 1e3:.3f} ms")
    print(f"effective sample rate: {1/np.mean(df_ip):.1f} fps")

    if show_plots:
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


if __name__ == "__main__":
    test_script()
