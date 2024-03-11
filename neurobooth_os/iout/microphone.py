import os

from pylsl import StreamInfo, StreamOutlet, local_clock
import pyaudio
import numpy as np
import threading
import time
import uuid
import wave
import logging

from neurobooth_os.iout.stim_param_reader import MicYetiDeviceArgs
from neurobooth_os.iout.stream_utils import DataVersion, set_stream_description
from neurobooth_os.log_manager import APP_LOG_NAME


class MicStream:
    def __init__(
        self,
        device_args: MicYetiDeviceArgs,
        CHANNELS=1,
        FORMAT=pyaudio.paInt16,
        save_on_disk=False,
    ):
        device_id = device_args.device_id
        # There should always be one and only one sensor for the mic
        sensor = device_args.sensor_array[0]
        self.CHUNK = sensor.CHUNK
        self.fps = sensor.RATE
        self.sensor_ids = device_args.sensor_ids
        self.save_on_disk = save_on_disk
        self.CHANNELS = CHANNELS
        self.FORMAT = FORMAT
        # Create audio object
        audio = pyaudio.PyAudio()
        self.p = audio
        self.last_time = local_clock()
        # Get Blue Yeti mic device ID
        info = audio.get_host_api_info_by_index(0)
        dev_inx = -1
        for i in range(info.get("deviceCount")):
            if (
                audio.get_device_info_by_host_api_device_index(0, i).get(
                    "maxInputChannels"
                )
            ) > 0:
                dev_name = audio.get_device_info_by_host_api_device_index(0, i).get("name")
                print("Device name: " + dev_name)
                if device_args.microphone_name in dev_name:  # replace with Samson if using Samson mic
                    dev_inx = i
                    self.device_name = dev_name
                    break

        # Create stream
        self.stream_in = audio.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=sensor.RATE,
            input=True,
            output=True,
            frames_per_buffer=sensor.CHUNK,
            input_device_index=dev_inx,
        )

        # Setup outlet stream infos
        self.oulet_id = str(uuid.uuid4())
        self.stream_info_audio = set_stream_description(
            stream_info=StreamInfo("Audio", "Experimental", sensor.CHUNK + 1, sensor.RATE / sensor.CHUNK, "int16", self.oulet_id),
            device_id=device_args.device_id,
            sensor_ids=device_args.sensor_ids,
            data_version=DataVersion(1, 0),
            columns=['ElapsedTime', f'Amplitude ({sensor.CHUNK} samples)'],
            column_desc={
                'ElapsedTime': 'Elapsed time on the local LSL clock since the last chunk of samples (ms)',
                f'Amplitude ({sensor.CHUNK} samples)': 'Remaining columns represent a chunk of audio samples.',
            },
            contains_chunks=True,
            fps=str(self.fps),
            device_name=device_args.device_name,
        )
        print(f"-OUTLETID-:Audio:{self.oulet_id}")

        self.logger = logging.getLogger(APP_LOG_NAME)
        self.logger.debug(
            f'Microphone: sample_rate={str(self.fps)}; save_on_disk={self.save_on_disk}; channels={self.CHANNELS}'
        )

        self.streaming = False
        self.stream_on = False
        self.tic = 0
        self.outlet_audio = StreamOutlet(self.stream_info_audio)

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
        print("Microphone stream opened")
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
        print("Microphone stream closed")
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


# for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
#     data = stream.read(CHUNK)
#     frames.append(data)

# print("* done recording")

# stream.stop_stream()
# stream.close()
# p.terminate()

# wf = wave.open(WAVE_OUTPUT_FILENAME, 'wb')
# wf.setnchannels(CHANNELS)
# wf.setsampwidth(p.get_sample_size(FORMAT))
# wf.setframerate(RATE)
# wf.writeframes(b''.join(frames))
# wf.close()
