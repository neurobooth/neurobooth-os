import os

from pylsl import StreamInfo, StreamOutlet, local_clock
import pyaudio
import numpy as np
import threading
import time
import uuid
import wave
import logging
from typing import NamedTuple, List, Optional

from neurobooth_os.iout.stim_param_reader import MicYetiDeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME


class AudioDeviceInfo(NamedTuple):
    index: int
    max_input_channels: Optional[float]
    name: str


class AudioDeviceException(Exception):
    """Exception thrown for errors finding the correct audio device."""
    pass


class MicStream:
    def __init__(
        self,
        device_args: MicYetiDeviceArgs,
        CHANNELS=1,
        FORMAT=pyaudio.paInt16,
        save_on_disk=False,
    ):
        # There should always be one and only one sensor for the mic
        sensor = device_args.sensor_array[0]
        self.CHUNK = sensor.sample_chunk_size
        self.fps = sensor.sample_rate
        self.sensor_ids = device_args.sensor_ids
        self.save_on_disk = save_on_disk
        self.CHANNELS = CHANNELS
        self.FORMAT = FORMAT

        self.logger = logging.getLogger(APP_LOG_NAME)

        # Create audio object
        audio = pyaudio.PyAudio()
        self.p = audio
        self.last_time = local_clock()

        # Identify the correct device
        device = MicStream.find_matching_audio_device(device_args, MicStream.get_audio_devices(audio))
        self.logger.debug(f'Using audio device "{device.name}" at index {device.index}.')
        self.device_name = device.name

        # Create stream
        self.stream_in = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=sensor.sample_rate,
            input=True,
            output=True,
            frames_per_buffer=sensor.sample_chunk_size,
            input_device_index=device.index,
        )

        # Setup outlet stream infos
        self.oulet_id = str(uuid.uuid4())
        self.stream_info_audio = set_stream_description(
            stream_info=StreamInfo("Audio", "Experimental", sensor.sample_chunk_size + 1,
                                   sensor.sample_rate / sensor.sample_chunk_size, "int16", self.oulet_id),
            device_id=device_args.device_id,
            sensor_ids=device_args.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['ElapsedTime', f'Amplitude ({sensor.sample_chunk_size} samples)'],
            column_desc={
                'ElapsedTime': 'Elapsed time on the local LSL clock since the last chunk of samples (ms)',
                f'Amplitude ({sensor.sample_chunk_size} samples)': 'Remaining columns represent a chunk of audio samples.',
            },
            contains_chunks=True,
            fps=str(self.fps),
            device_name=device_args.device_name,
        )
        print(f"-OUTLETID-:Audio:{self.oulet_id}")
        self.logger.debug(
            f'Microphone: sample_rate={str(self.fps)}; save_on_disk={self.save_on_disk}; channels={self.CHANNELS}'
        )

        self.streaming = False
        self.stream_on = False
        self.tic = 0
        self.outlet_audio = StreamOutlet(self.stream_info_audio)

    @staticmethod
    def get_audio_devices(audio: pyaudio.PyAudio, host_api_idx: int = 0) -> List[AudioDeviceInfo]:
        """
        Extract information about audio devices from PyAudio.
        :param audio: A PyAudio object.
        :param host_api_idx: The host_api_index to be passed to PyAudio.
        :return: A list of identified audio devices.
        """
        return [
            AudioDeviceInfo(
                index=i,
                max_input_channels=audio.get_device_info_by_host_api_device_index(host_api_idx, i).get('maxInputChannels'),
                name=audio.get_device_info_by_host_api_device_index(host_api_idx, i).get('name'),
            )
            for i in range(audio.get_host_api_info_by_index(host_api_idx).get("deviceCount"))
        ]

    @staticmethod
    def find_matching_audio_device(
            device_args: MicYetiDeviceArgs, device_info: List[AudioDeviceInfo]
    ) -> AudioDeviceInfo:
        """
        Identify audio devices matching the device arguments.
        :param device_args: The device arguments to check against.
        :param device_info: A list of audio devices found by get_audio_devices.
        :return: The matching audio device. An error is raised if no or multiple devices are found.
        """
        device_info = [  # Filter list to matching name and sufficient channels
            dev for dev in device_info
            if (device_args.microphone_name in dev.name) and (dev.max_input_channels > 0)
        ]
        if len(device_info) == 0:
            raise AudioDeviceException('No matching audio devices found!')
        if len(device_info) > 1:
            dev_names = ', '.join([f'"{dev.name}"' for dev in device_info])
            raise AudioDeviceException(f'Ambiguous audio device specification. Matches: {dev_names}')
        return device_info[0]

    def start(self):
        # Create outlets

        self.streaming = True
        self.stream_on = True
        if self.save_on_disk:
            self.frames = []
            self.frames_raw = []
        self.stream_thread = threading.Thread(target=self.stream)
        self.logger.debug('Microphone: Starting LSL Thread')
        self.stream_thread.start()

    def stream(self):
        self.last_time = int(local_clock() * 10e3)
        self.logger.debug('Microphone: Entering LSL Loop')
        while self.streaming:
            data = self.stream_in.read(self.CHUNK)
            decoded = np.frombuffer(data, "int16")

            tlocal = int((local_clock() * 10e3))
            tdiff = tlocal - self.last_time
            self.last_time = tlocal

            decoded = np.hstack((np.array(tdiff), decoded))

            if self.save_on_disk:
                self.frames_raw.append(data)
                self.frames.append(decoded)

            try:
                self.outlet_audio.push_sample(decoded)
            except BaseException:  # "OSError" from C++
                print("Reopening mic stream already closed")
                self.outlet_audio = StreamOutlet(self.stream_info_audio)
                self.outlet_audio.push_sample(decoded)
            self.tic = time.time()
        self.stream_on = False
        self.logger.debug('Microphone: Exiting LSL Thread')

    def stop(self):
        self.logger.debug('Microphone: Setting Stop Signal')
        self.streaming = False
        if self.save_on_disk:
            self.logger.debug('Microphone: Saving Data to Disk...')

            wf = wave.open("decoded_mic_data.wav", "wb")
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(self.FORMAT))
            wf.setframerate(self.fps)
            wf.writeframes(b"".join(self.frames))
            wf.close()
            self.logger.debug('Microphone: Saved Decoded Data to Disk')

            wf = wave.open("raw_mic_data.wav", "wb")
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(self.FORMAT))
            wf.setframerate(self.fps)
            wf.writeframes(b"".join(self.frames_raw))
            wf.close()
            self.logger.debug('Microphone: Saved Raw Data to Disk')
