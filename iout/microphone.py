from pylsl import StreamInfo, StreamOutlet
import pyaudio
import numpy as np
import threading
import time


class MicStream():
    def __init__(self, CHANNELS=1, RATE=44100,  CHUNK=1024, SAMPLE_RATE=200,
                 FORMAT=pyaudio.paFloat32):
       
        self.CHUNK = CHUNK
        
        # Create audio object
        audio = pyaudio.PyAudio()
    
        # Create stream
        self.stream_in = audio.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 output=True,
                                 frames_per_buffer=CHUNK)
    
        # Setup outlet stream infos
        self.stream_info_audio = StreamInfo('Audio', 'Experimental', CHUNK, RATE/CHUNK,
                                       'float32', 'audioid_1')
        
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
            decoded = np.frombuffer(data, 'Float32')
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



        #try:
       #     self.outlet_audio.__del__()
        #except:# AttributeError:
         #   print("AttributeError mic outlet")
            
                
