from pynput import mouse
from pylsl import StreamInfo, StreamOutlet



class MouseStream():
    def __init__(self):
        
        info = StreamInfo(name='Mouse', type='mouse', channel_count=2, 
                          channel_format='int32',source_id='myuid34234')
        
        self.outlet = StreamOutlet(info)
    
        self.streaming = False
        
        
    def start(self):
        self.streaming = True        
        self.stream()
        self.listener.start()
        
        
    def stream(self):
        
        def on_move(x, y):
            mysample = [x,y]
            self.outlet.push_sample(mysample)    
            
        self.listener = mouse.Listener(on_move=on_move)
        
                       
    def stop(self):
        self.streaming = False        
        self.listener.stop()
    
