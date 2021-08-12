from pylsl import StreamInfo, StreamOutlet
import pyaudio
import numpy as np
import threading
import time
import uuid


class MicStream():
    def __init__(self, CHANNELS=1, RATE=44100,  CHUNK=1024,
                 FORMAT=pyaudio.paFloat32):
       
        self.CHUNK = CHUNK
        self.fps = RATE
        # Create audio object
        audio = pyaudio.PyAudio()
        
        # Get Blue Yeti mic device ID
        info = audio.get_host_api_info_by_index(0)        
        for i in range(info.get('deviceCount')):
                if (audio.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                    dev_name = audio.get_device_info_by_host_api_device_index(0, i).get('name')
                    if "BLUE USB" in dev_name:
                        dev_inx = i
                        self.device_name = dev_name
                        break

        # Create stream
        self.stream_in = audio.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 output=True,
                                 frames_per_buffer=CHUNK,
                                 input_device_index=dev_inx)
    
        # Setup outlet stream infos
        self.oulet_id =  str(uuid.uuid4())
        self.stream_info_audio = StreamInfo('Audio', 'Experimental', CHUNK, RATE/CHUNK,
                                       'float32', self.oulet_id)
        
        self.stream_info_audio.desc().append_child_value("fps", str(self.fps))
        self.stream_info_audio.desc().append_child_value("device_name", self.device_name)
        print(f"-OUTLETID-:Audio:{self.oulet_id}")
        
        self.streaming = False
        self.stream_on = False
        self.tic = 0
        
    def start(self):
        # Create outlets
        self.outlet_audio = StreamOutlet(self.stream_info_audio)
        self.streaming = True
        self.stream_on = True
        self.stream_thread = threading.Thread(target=self.stream)
        self.stream_thread.start()
    
    
    def stream(self):
        print("Microphone stream opened")
        while self.streaming:
            data = self.stream_in.read(self.CHUNK)
            decoded = np.frombuffer(data, 'float32')
            try:
                self.outlet_audio.push_sample(decoded)
            except:  # "OSError" from C++
                print("Reopening mic stream already closed")
                self.outlet_audio = StreamOutlet(self.stream_info_audio)
                self.outlet_audio.push_sample(decoded)
            self.tic =  time.time()
        self.stream_on = False
        print("Microphone stream closed")


    def stop(self):
        self.streaming = False


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
            
                
