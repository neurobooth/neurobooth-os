from pylsl import StreamInfo, StreamOutlet
import time


def marker_stream():
    
    ''' Create marker stream to be pushed when needed with a string format: 
        "%s_%d_%timestamp" aka code string, number, time'''
    
    # Setup outlet stream infos
    stream_info_marker = StreamInfo('Marker', 'Markers', 1, 
                                    channel_format='string', source_id ='marker')
    
    # Create outlets
    outlet_marker = StreamOutlet(stream_info_marker)
    
    outlet_marker.push_sample([f"Streaming_0_{time.time()}"])
    
    return outlet_marker 
