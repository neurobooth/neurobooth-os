from pynput import mouse
from pylsl import StreamInfo, StreamOutlet



class MouseStream():
    def __init__(self):
        
        info_stream = StreamInfo(name='Mouse', type='mouse', channel_count=3, 
                          channel_format='int32',source_id='myuid34234')
        
        self.info_stream = info_stream
        self.outlet = StreamOutlet(info_stream)
    
        self.streaming = False
        
        
    def start(self):
        self.streaming = True        
        self.stream()
        self.listener.start()
        
        try:
            self.outlet.push_sample([0,0,0])
        except:  # "OSError" from C++
            print("Reopening stream already closed")
            self.outlet = StreamOutlet(self.info_stream)
                
                
    def stream(self):
        
        def on_move(x, y):
            mysample = [x,y,0]
            try:
                self.outlet.push_sample(mysample)#, timestamp=time.time())   
            except:#  OSError:
                print("Mouse listner caugh error pushing oulet, mouse move")
            
        def on_click(x, y, button, pressed):
            state = 1 if pressed else -1
            mysample = [x,y,state]   
            try:
                self.outlet.push_sample(mysample)#, timestamp=time.time())  
            except:# OSError:
                print("Mouse listner caugh error pushing oulet, click")

        self.listener = mouse.Listener(on_move=on_move, on_click=on_click)
        
                       
    def stop(self):
        self.streaming = False     
        try:
            self.listener.stop()
        except AttributeError:
            print("Never started to capture mouse")
                  
        self.outlet.__del__()