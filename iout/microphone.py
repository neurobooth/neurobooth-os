from pylsl import StreamInfo, StreamOutlet
import pyaudio
import numpy as np
import threading



class MicStream():
    def __init__(self, CHANNELS=1, RATE=44100,  CHUNK=1024, SAMPLE_RATE=200,
                 FORMAT=pyaudio.paFloat32):
       
        self.CHUNK = CHUNK
        
        # Create audio object
        audio = pyaudio.PyAudio()
    
        # Create stream
        self.stream = audio.open(format=FORMAT,
                                 channels=CHANNELS,
                                 rate=RATE,
                                 input=True,
                                 output=True,
                                 frames_per_buffer=CHUNK)
    
        # Setup outlet stream infos
        self.stream_info_audio = StreamInfo('Audio', 'Experimental', CHUNK, RATE/CHUNK,
                                       'float32', 'audioid_1')
        
        self.streaming = False
        
        
    def start():
        # Create outlets
        outlet_audio = StreamOutlet(stream_info_audio)
        self.streaming = True
        
        self.stream_thread = threading.Thread(target=self.stream)
        self.stream_thread.start()
    
    def stream():
        print("Microphone stream opened")
        while self.streaming:
            data = self.stream.read(self.CHUNK)
            decoded = np.fromstring(data, 'Float32')
            outlet_audio.push_sample(decoded)
        print("Microphone stream closed")

    def stop():
        self.streaming = False