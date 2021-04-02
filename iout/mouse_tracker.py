from pynput import mouse
from pylsl import StreamInfo, StreamOutlet
import time


class MouseStream():
    def __init__(self):
        
        info = StreamInfo(name='Mouse', type='mouse', channel_count=3, 
                          channel_format='int32',source_id='myuid34234')
        
        self.outlet = StreamOutlet(info)
    
        self.streaming = False
        
        
    def start(self):
        self.streaming = True        
        self.stream()
        self.listener.start()
        
        
    def stream(self):
        
        def on_move(x, y):
            mysample = [x,y,0]
            self.outlet.push_sample(mysample)#, timestamp=time.time())   
            
        def on_click(x, y, button, pressed):
            state = 1 if pressed else -1
            mysample = [x,y,state]           
            self.outlet.push_sample(mysample)#, timestamp=time.time())   
    
        self.listener = mouse.Listener(on_move=on_move, on_click=on_click)
        
                       
    def stop(self):
        self.streaming = False        
        self.listener.stop()
    
