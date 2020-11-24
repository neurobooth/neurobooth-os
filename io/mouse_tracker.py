from pynput import mouse
from pylsl import StreamInfo, StreamOutlet


def mouse_stream():
    task = 1.0
    
    def on_move(x, y):
        mysample = [x,y,task]
        outlet.push_sample(mysample)
    
    info = StreamInfo(name='Touchpad', type='mouse', channel_count=3, channel_format='float32',source_id='myuid34234')
    outlet = StreamOutlet(info)
    
    with mouse.Listener(on_move=on_move) as listener:
        listener.join()