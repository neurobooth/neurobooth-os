import time
import threading
import logging
import json
import random
import uuid
import struct
import base64
from typing import Optional, List, Tuple, ByteString

# Import dependencies from the user's provided file structure
try:
    from neurobooth_os.iout.iphone import IPhone, IPhoneDeviceArgs, IPhoneError, DISABLE_LSL
    from neurobooth_os.log_manager import APP_LOG_NAME
except ImportError:
    import logging

    APP_LOG_NAME = "neurobooth"
    DISABLE_LSL = False  # Set to False to try real LSL


    # Stub classes to allow compilation if dependencies are missing
    class IPhone:
        def __init__(self, name, sess_id="", mock=True, device_args=None):
            self.name = name
            self.iphone_sessionID = sess_id
            self.streamName = f"IPhone_{name}"
            self.connected = False
            self.streaming = False

        @staticmethod
        def send_file_msg(stream_name, filename):
            print(f"MOCK MSG: {stream_name} created file {filename}")


    class IPhoneDeviceArgs:
        pass


    class IPhoneError(Exception):
        pass

# Setup Real LSL imports
try:
    from pylsl import StreamInfo, StreamOutlet, local_clock

    HAS_LSL = True
except ImportError:
    local_clock = time.time
    HAS_LSL = False


class MockIPhone(IPhone):
    """
    A software-only simulation of the IPhone device.
    Uses REAL LSL if available, but mocks the hardware connection.
    Returns a valid JPEG binary for the preview.
    """

    def __init__(self, name, sess_id="", device_args: IPhoneDeviceArgs = None):
        # Initialize parent logic
        super().__init__(name, sess_id=sess_id, mock=True, device_args=device_args)

        self.logger = logging.getLogger(APP_LOG_NAME)
        self._mock_streaming_active = False
        self._mock_thread = None
        self._frame_counter = 0
        self._simulated_fps = 30.0

        # A tiny valid 1x1 gray JPEG image
        # This ensures the UI actually "sees" an image instead of corrupted data
        self._base_image = base64.b64decode(
            "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP////////////////////////////////////////////////////"
            "//////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPyGf/9k="
        )

        # Ensure locks exist (parent might not have them if it's the dummy class)
        if not hasattr(self, '_state_lock'):
            self._state_lock = threading.RLock()
        if not hasattr(self, 'ready_event'):
            self.ready_event = threading.Event()

        with self._state_lock:
            self._state = "#DISCONNECTED"

    def _create_outlet(self) -> 'StreamOutlet':
        """
        Creates a real LSL outlet.
        Replicates the logic from iphone.py to ensure the mock is self-contained.
        """
        if not HAS_LSL:
            raise ImportError("pylsl not installed. Cannot create real LSL outlet.")

        self.logger.info(f"MockIPhone: Creating REAL LSL outlet for {self.streamName}")
        info = StreamInfo(
            name=self.streamName,
            type='Markers',
            channel_count=3,
            nominal_srate=30,
            channel_format='double64',
            source_id=str(uuid.uuid4())
        )
        # Add metadata similar to real iPhone
        xml = info.desc()
        xml.append_child_value("device_name", "MockIPhone")
        xml.append_child_value("serial_number", "MOCK_12345")

        return StreamOutlet(info)

    def prepare(self, mock: bool = False, config: Optional[dict] = None) -> bool:
        """
        Mock preparation. Skips hardware connection.
        """
        self.logger.info("MockIPhone: Preparing device (Software Simulation)")

        with self._state_lock:
            self._state = "#READY"

        self.connected = True

        if not DISABLE_LSL:
            try:
                # Use local _create_outlet if parent's one is missing
                create_fn = getattr(super(), "_create_outlet", self._create_outlet)
                self.outlet = create_fn()
                self.logger.info(f"MockIPhone: LSL Outlet active (Stream: {self.streamName}).")
            except Exception as e:
                self.logger.error(f"MockIPhone: Failed to create LSL outlet: {e}")
                return False

        return True

    def start(self, filename: str) -> None:
        self.logger.info(f"MockIPhone: Start recording to {filename}")

        with self._state_lock:
            self._state = "#RECORDING"

        self.streaming = True
        self._mock_streaming_active = True

        self._mock_thread = threading.Thread(target=self._simulate_data_stream)
        self._mock_thread.daemon = True
        self._mock_thread.start()

        if not DISABLE_LSL:
            time.sleep(0.1)
            f_base = f"{filename}_IPhone"
            IPhone.send_file_msg(self.streamName, f"{f_base}.mov")
            IPhone.send_file_msg(self.streamName, f"{f_base}.json")

    def stop(self) -> None:
        self.logger.info("MockIPhone: Stopping recording")
        self._mock_streaming_active = False
        self.streaming = False

        if self._mock_thread and self._mock_thread.is_alive():
            self._mock_thread.join(timeout=1.0)

        with self._state_lock:
            self._state = "#READY"
            self.ready_event.set()

    def frame_preview(self) -> ByteString:
        """
        Returns a valid JPEG image (binary).
        We append random noise to the end to reach ~1000 bytes.
        """
        self.logger.debug("MockIPhone: Frame preview requested")

        image_data = self._base_image
        target_size = 1000 + random.randint(-50, 50)
        padding_size = max(0, target_size - len(image_data))

        # We avoid using struct.pack with f-strings here to bypass the backslash error
        padding = bytes([random.randint(0, 255) for _ in range(padding_size)])

        return image_data + padding

    def dumpall_getfilelist(self) -> Tuple[Optional[List[str]], Optional[List[str]]]:
        fake_filename = f"{self.iphone_sessionID}_mock_video.mov"
        fake_hash = "mock_hash_123"
        return [fake_filename], [fake_hash]

    def dump(self, filename: str, expected_hash: str, timeout_sec: Optional[float] = None) -> ByteString:
        return b"MOCK_VIDEO_FILE_CONTENT"

    def dump_success(self, filename: str) -> None:
        self.logger.info(f"MockIPhone: File {filename} dump success")

    def disconnect(self, join_listener: bool = True) -> bool:
        self._mock_streaming_active = False
        self.connected = False
        with self._state_lock:
            self._state = "#DISCONNECTED"
        return True

    def _simulate_data_stream(self):
        while self._mock_streaming_active:
            loop_start = local_clock()
            if not DISABLE_LSL and hasattr(self, 'outlet'):
                self._frame_counter += 1
                # [Frame, DeviceTime, AcqTime]
                sample = [float(self._frame_counter), local_clock(), time.time()]
                self.outlet.push_sample(sample)

            elapsed = local_clock() - loop_start
            sleep_time = (1.0 / self._simulated_fps) - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"LSL Library Found: {HAS_LSL}")

    mock_phone = MockIPhone("MockPhone", sess_id="test_sess")
    if mock_phone.prepare():
        img = mock_phone.frame_preview()
        # Fixed logic check for print
        is_jpeg = img.startswith(b'\xff\xd8')
        print(f"Preview generated: {len(img)} bytes. Starts with JPEG SOI: {is_jpeg}")
        mock_phone.start("test_file")
        time.sleep(1)
        mock_phone.stop()
        mock_phone.disconnect()