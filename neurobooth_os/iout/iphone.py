import os.path as op
from email import message_from_string
from functools import partial
from logging import raiseExceptions
from multiprocessing import Condition
import matplotlib
matplotlib.use('TKAgg')
import socket
import json
import struct
import threading
import time
from datetime import datetime
import select
import uuid
from pylsl import StreamInfo, StreamOutlet
import liesl

from neurobooth_os.iout.usbmux import  USBMux


IPHONE_PORT=2345 #IPhone should have socket on this port open, if we're connecting to it.

class IPhoneError(Exception):
    pass

class IPhoneListeningThread(threading.Thread):
    def __init__(self,*args):
        self._iphone=args[0]
        self._running=True
        threading.Thread.__init__(self)

    def run(self):
        while self._running:
            try:
                msg,version,type,resp_tag=self._iphone._getpacket()                
                self._iphone._process_message(msg,resp_tag)
                #if resp_tag==0:
                    #print(f'Listener received: {msg}')
                #else:
                   #print(f'Listener received: Tag {resp_tag}')
            except:
                pass
            
    def stop(self):
        self._running=False


class IPhone:
    TYPE_MESSAGE=101
    VERSION=1
    STATE_TRANSITIONS={'#DISCONNECTED':{'@HANDSHAKE':'#CONNECTED','@ERROR':'#ERROR'},
                        '#CONNECTED':{'@STANDBY':'#STANDBY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#PREVIEW':{'@PREVIEWRECEIVE':'#READY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#DUMPALL':{'@FILESTODUMP':'#READY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'}, #NO SPECIAL state for after received ready to dump. Dump is done from 'Connected' state
                        '#DUMP':{'@DUMPRECEIVE':'#READY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#STANDBY':{'@READY':'#READY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#READY':{'@START':'#START','@PREVIEW':'#PREVIEW','@DUMPALL':'#DUMPALL','@DUMP':'#DUMP','@DUMPSUCCESS':'#READY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#START':{'@STARTTIMESTAMP':'#RECORDING','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#RECORDING':{'@INPROGRESSTIMESTAMP':'#RECORDING','@STOP':'#STOP','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#STOP':{'@STOPTIMESTAMP':'#READY','@DISCONNECT':'#DISCONNECTED','@ERROR':'#ERROR'},
                        '#ERROR':{'@DISCONNECT':'#DISCONNECTED'}
                    }
    MESSAGE_TYPES=[]
    for elem in STATE_TRANSITIONS:
        MESSAGE_TYPES+=STATE_TRANSITIONS[elem].keys()
    MESSAGE_TYPES=set(MESSAGE_TYPES)
#    print(MESSAGE_TYPES)
#    MESSAGE_TYPES=set(['@START','@STOP','@STANDBY','@READY','@PREVIEW','@DUMP','@STARTTIMESTAMP','@INPROGRESSTIMESTAMP','@STOPTIMESTAMP','@DUMPALL','@DISCONNECT','@FILESTODUMP'])
    MESSAGE_KEYS=set(['MessageType','SessionID','TimeStamp','Message'])
    
    def __init__(self,name,sess_id='',mock=False,device_id='',sensor_ids=''):
        self.connected=False
        self.recording=False
        self.tag=0
        self.iphone_sessionID=sess_id
        self._allmessages=[]
        self.name=name
        self.mock=mock
        self.device_id=device_id
        self.sensor_ids=sensor_ids
        self._state='#DISCONNECTED'
        self._frame_preview_data=b''
        self._frame_preview_cond=Condition()
        self._dump_video_data=b''
        self._dump_video_cond=Condition()
        self._wait_for_reply_cond=Condition()
        self._msg_latest={}
        self._timeout_cond=5
        self.outlet = self.createOutlet()

    def _validate_message(self,message,tag):
        
        if tag==1: # TAG==1 corresponds to PREVIEW file receiving
            msgType='@PREVIEWRECEIVE'
        elif tag==2:
            msgType='@DUMPRECEIVE'
        elif tag!=0:
            print(f'Incorrect tag received from IPhone. Tag={tag}')
            self.disconnect()
            return False
            #raise IPhoneError(f'Incorrect tag received from IPhone. Tag={tag}')
        else:
            if len(message)!=len(self.MESSAGE_KEYS):
                print(f'Message has incorrect length: {message}')
                self.disconnect()
                return False
                #raise IPhoneError(f'Message has incorrect length: {message}')
            for key in message:
                if key not in self.MESSAGE_KEYS:
                    print(f'Message has incorrect key: {key} not allowed. {message}')
                    self.disconnect()
                    return False
                    #raise IPhoneError(f'Message has incorrect key: {key} not allowed. {message}')
            msgType=message['MessageType']
        # print(f'Initial State: {self._state}')
        # print(f'Message: {msgType}')
        #validate whether the transition is valid
        allowed_trans=self.STATE_TRANSITIONS[self._state]
        if msgType in allowed_trans:
            self._state=allowed_trans[msgType]
        else:
            print(f'Message {msgType} is not valid in the state {self._state}.')
            self.disconnect()
            return False
            #raise IPhoneError(f'Message {msgType} is not valid in the state {self._state}.')
        # print(f'Outcome State:{self._state}')
        return True

    def _message(self,msg_type,ts='',msg=''):
        if not msg_type in self.MESSAGE_TYPES:
            raise IPhoneError(f'Message type "{msg_type}" not in allowed message type list')
        return {"MessageType": msg_type,
            "SessionID": self.iphone_sessionID,
            "TimeStamp": ts,
            "Message": msg
        }
    def _json_wrap(self,message):
        json_msg=json.dumps(message)
        json_msg='####'+json_msg # add 4 bytes
        return json_msg
    def _json_unwrap(self,payload):
        message=json.loads(payload[4:])
        return message

    def _sendpacket(self,msg_type,msg_contents=None,cond=None):
#        if not self.connected:
#            raise IPhoneError('IPhone is not connected')
        msg=self._message(msg_type)
        if not msg_contents is None:
            # replace contents of msg with information from provided dict
            for key in msg_contents:
                msg[key]=msg_contents[key]
        if not self._validate_message(msg,0):
            print(f'Message {msg} did not pass validation. Exiting _sendpacket.')
            self.disconnect()
            return False
               #do transition through validate_message
        self._process_message(msg,self.tag)
        payload=self._json_wrap(msg).encode('utf-8')
        payload_size=len(payload)
        packet=struct.pack("!IIII",self.VERSION,self.TYPE_MESSAGE,self.tag,payload_size)+payload

        if not cond is None:
            cond.acquire()
            self.sock.send(packet)
            if not cond.wait(timeout=self._timeout_cond):
                cond.release()
                print(f'No reply received from the device after packet {msg_type} was sent.')
                #self.disconnect()
                return False
            cond.release()
        else:
            self.sock.send(packet)
        return True


    def recvall(self,sock, n):
    # Helper function to recv n bytes or return None if EOF is hit
        fragments = []
        BUFF_SIZE=16384
        MAX_RECV = 130992
        buff_recv=0 
        while True: 
            bytes_to_pull = n
            if (n - buff_recv) < MAX_RECV:
                bytes_to_pull = n - buff_recv            
            packet = sock.recv(bytes_to_pull)
            buff_recv += len(packet)
            fragments.append(packet)
            if buff_recv >= n :
                break
        data=b''.join(fragments)
        return data

    def _getpacket(self,timeout_in_seconds=20):
        ready,_,_ = select.select([self.sock], [], [], timeout_in_seconds)
        #print(ready)
        if ready:
            first_frame=self.sock.recv(16)
            version,type,tag,payload_size = struct.unpack("!IIII", first_frame)

            if tag == 1 or tag == 2:
                self._validate_message({},tag)
                payload=self.recvall(self.sock,payload_size)
                return payload,version,type,tag
            else:
                payload = self.sock.recv(payload_size)

#PROCESS TAG 1 and 2
        #Tag  = 0
            msg=self._json_unwrap(payload)
            self._validate_message(msg,tag)
            return msg,version,type,tag
        else:
            raise IPhoneError(f'Timeout for packet receive exceeded ({timeout_in_seconds} sec)')

    def handshake(self,config):
        if self._state!='#DISCONNECTED':
            print('Handshake is only available when disconnected')
            return False
        self.usbmux=USBMux()
        if not self.usbmux.devices:
            self.usbmux.process(0.1)
        for dev in self.usbmux.devices:
            print(dev)
        if len(self.usbmux.devices)==1:
            self.device=self.usbmux.devices[0]
            self.sock=self.usbmux.connect(self.device,IPHONE_PORT)
            self._state='#CONNECTED'
            
            #as soon as we're connected - start parallel listening thread.
            self._listen_thread=IPhoneListeningThread(self)
            self._listen_thread.start()
            #self.sock.setblocking(0)
            self.connected=True
#            self.notifyonframe=1
            # Create config 
            
            msg_camera_config={'Message':json.dumps(config)}
            print(msg_camera_config)
            self._sendpacket('@STANDBY',msg_contents=msg_camera_config,cond=self._wait_for_reply_cond)
            return True
        else:
            return False

    def _mock_handshake(self):
        tag=self.tag
        self._sendpacket('@STANDBY')
        msg,version,type,resp_tag=self._getpacket()
        self._validate_message(msg)
        if msg['MessageType']!='@READY':
            self.sock.close() #close the socket on our side to avoid hanging sockets
            raise IPhoneError('Cannot establish STANDBY->READY connection with Iphone')
        # if tag!=resp_tag (check with Steven)
        #process message - send timestamps to LSL, etc.
        self._process_message(msg,resp_tag)
        return 0    
    
    def start_recording(self,filename):
#        if not self.connected:
#            raise IPhoneError('IPhone not connected when start_recording is called.')
#        tag=self.tag
        msg_filename={'Message':filename}
        self._sendpacket('@START',msg_contents=msg_filename,cond=self._wait_for_reply_cond)
        return 0
    
    def stop_recording(self):
        self._sendpacket('@STOP',cond=self._wait_for_reply_cond)
        return 0 
    
    def _process_message(self,msg,tag):
        if tag==1:
            self._frame_preview_cond.acquire()
            self._frame_preview_data=msg
            self._frame_preview_cond.notify()
            self._frame_preview_cond.release()
#            return msg #msg is binary data - image
        elif tag==2:
            self._dump_video_cond.acquire()
            self._dump_video_data=msg
            self._dump_video_cond.notify()
            self._dump_video_cond.release()
#            return msg #msg is binary data - video
        else:
            self._wait_for_reply_cond.acquire()
            self._msg_latest=msg
            self._wait_for_reply_cond.notify()
            self._wait_for_reply_cond.release()
            self._allmessages.append({'message':msg,'ctr_timestamp':str(datetime.now()),'tag':tag})

        if msg['MessageType']=='@STARTTIMESTAMP':
            self.fcount=0
            # print([self.fcount, float(msg['TimeStamp']), time.time()])
            self.outlet.push_sample([self.fcount, float(msg['TimeStamp']), time.time()])       
        elif msg['MessageType'] in ['@INPROGRESSTIMESTAMP','@STOPTIMESTAMP']:
            self.fcount+=self.notifyonframe
            # print([self.fcount, float(msg['TimeStamp']), time.time()])
            self.outlet.push_sample([self.fcount, float(msg['TimeStamp']), time.time()])       

    def createOutlet(self):
        self.streamName = 'IPhoneFrameIndex'
        self.oulet_id = str(uuid.uuid4())
        info = StreamInfo(name=self.streamName, type='videostream', channel_format='double64',
            channel_count=3, source_id=self.oulet_id)

        info.desc().append_child_value("device_id", self.device_id)
        info.desc().append_child_value("sensor_ids", str(self.sensor_ids))
        # info.desc().append_child_value("fps_rgb", str(self.fps))
        col_names = ['frame_index', 'iphone_frame_timestamp', 'unix_timestamp']
        info.desc().append_child_value("column_names", str(col_names))  

        print(f"-OUTLETID-:{self.streamName}:{self.oulet_id}")
        return StreamOutlet(info)

    def frame_preview(self):
        self._frame_preview_data=b''
        self._sendpacket('@PREVIEW',cond=self._frame_preview_cond)
        return self._frame_preview_data
    
    def start(self,filename):
        self.streaming=True
        filename += "_IPhone"
        filename = op.split(filename)[-1]
        print(f"-new_filename-:{self.streamName}:{filename}")        
        self.start_recording(filename)
        
    def stop(self):
        self.stop_recording()
        self.streaming=False
    
    def close(self):
        self.disconnect()
        
    def prepare(self,mock=False,config=None):
        if mock:
            HOST = '127.0.0.1'                 # Symbolic name meaning the local host
            PORT = 50009     # Arbitrary non-privileged port
            s = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            s.connect((HOST,PORT))
            self.sock=s
            self._mock_handshake()
            self.connected=True
        else:
            if config is None:
                self.notifyonframe=10
                config={'NOTIFYONFRAME':str(self.notifyonframe),
                            'VIDEOQUALITY':'AVAssetExportPresetHighestQuality',
                            'USECAMERAFACING':'BACK','FPS':'60'}
            self.notifyonframe=int(config['NOTIFYONFRAME'])
            self.handshake(config)
        
    def dump(self,filename):
        self._dump_video_data=b''
        msg_filename={'Message':filename}
        self._sendpacket('@DUMP',msg_filename,cond=self._dump_video_cond)
        return self._dump_video_data

    def dumpsuccess(self,filename):
        msg_filename={'Message':filename}
        self._sendpacket('@DUMPSUCCESS',msg_filename)
        return True
        
    def disconnect(self):
        if self._state=='#DISCONNECTED':
            print('IPhone device is already disconnected')
            return False
        self._sendpacket('@DISCONNECT')
        time.sleep(4)
        self.sock.close()
        self._listen_thread.stop()
        self._listen_thread.join(timeout=3)
        if self._listen_thread.is_alive():
            raise IPhoneError('Cannot stop the recording thread')
        self.connected=False
        return True

    def dumpall_getfilelist(self):
        self._sendpacket('@DUMPALL',cond=self._wait_for_reply_cond)
        filelist=self._msg_latest['Message']
        if self._state=='#ERROR':
            return None
        return filelist

if __name__ == "__main__":
    
    import time
    # Creating and starting mock streams:
    iphone = IPhone("iphone")
    config={'NOTIFYONFRAME':'1',
                            'VIDEOQUALITY':'AVAssetExportPresetHighestQuality',
                            'USECAMERAFACING':'BACK','FPS':'60'}
    iphone.prepare(config=config)

    # frame = iphone.frame_preview()
    
    streamargs = {'name': "IPhoneFrameIndex"}
    recording_folder = ""
    subject = "007"
    session = liesl.Session(prefix=subject,
                            streamargs=[streamargs], mainfolder=recording_folder)

    session.start_recording()    
    iphone.start(subject + f"_task_obs_1_{time.time()}")
    
    time.sleep(10)

    iphone.stop()
    session.stop_recording()
    iphone.disconnect()
    import pyxdf
    import glob
    import numpy as np
    
    path = 'd:\\projects\\Github\\neurobooth-os\\neurobooth_os\\iout'
    fname = glob.glob(f"{path}/{subject}/recording_R0*.xdf")[-1]
    data, header = pyxdf.load_xdf(fname)

    ts = data[0]['time_series']
    ts_pc = [t[1] for t in ts]
    ts_ip = [t[2] for t in ts]
    
    df_pc = np.diff(ts_pc)
    df_ip = np.diff(ts_ip)
    xxx
    import matplotlib.pyplot as plt
    plt.figure()
    plt.plot(df_pc)
    plt.plot(df_ip)
    plt.show()
    
    plt.figure()
    plt.scatter(df_pc, df_ip)

    plt.show()
    
    plt.figure()
    plt.hist(np.diff(ts_pc[1:])-np.diff(ts_ip[1:]), 20)
    
    print( 'mean diff diff ', np.mean(np.abs(np.diff(ts_pc[1:])-np.diff(ts_ip[1:]))))
    
    tstmp = data[0]['time_stamps']
    plt.hist(np.diff(tstmp[1:])-np.diff(ts_ip[1:]))
    
    plt.figure()
    plt.hist(df_ip, 50)
"""

    MOCK=False

    iphone=IPhone('123456',sess_id='')
    iphone.handshake() # Sends "@STANDBY" -> waits for "@READY" 
    #iphone.dumpall('/Users/dmitry/data/tmp')
#    time.sleep(10)

#    video=iphone.dump('data_file_mar23_10')
#    f=open('/Users/dmitry/data/tmp/video_mar28_1.mp4','wb')
#    f.write(video)
#    f.close()
    

#     image=iphone.frame_preview()
#     f=open('image_mar28_frame_preview.png','wb')
#     f.write(image)
#     f.close()

#     iphone.start_recording('data_file_mar30_2000') # Starts Listening thread. Sends "@START" -> expects "@STARTTIMESTAMP"
# #    iphone.frame_preview()
#     time.sleep(5) # 30 sec sleep - in the meantime Listening thread catches "@INPROGRESSTIMESTAMP"
#     iphone.stop_recording() #Sends "@STOP" -> expects "@STOPTIMESTAMP". Closes the Listening thread
#     # iphone.disconnect()
#     iphone.disconnect()
#     exit(0)   
#    iphone.handshake()
    iphone.start_recording('data_file_mar28_4000') # Starts Listening thread. Sends "@START" -> expects "@STARTTIMESTAMP"
    #iphone.handshake()
    time.sleep(5) # 30 sec sleep - in the meantime Listening thread catches "@INPROGRESSTIMESTAMP"
    iphone.stop_recording() #Sends "@STOP" -> expects "@STOPTIMESTAMP". Closes the Listening thread
 #   iphone.disconnect()

 #   iphone.handshake()
    # iphone.stop_recording()
    iphone.start_recording('data_file_mar28_3000') # Starts Listening thread. Sends "@START" -> expects "@STARTTIMESTAMP"
    time.sleep(5) # 30 sec sleep - in the meantime Listening thread catches "@INPROGRESSTIMESTAMP"
    iphone.stop_recording() #Sends "@STOP" -> expects "@STOPTIMESTAMP". Closes the Listening thread
    iphone.disconnect()

    print(iphone._allmessages)

    #video=iphone.dump('STEVEN_FILE2022')
    #f=open('video.mp4','wb')
    #video=json.dumps(video).encode('utf-8')

    #f.write(video)
    #f.close()
    #iphone.disconnect()
    


'''        print(filelist)
        for fname in filelist:
            video,version,type,tag=self._getpacket()
            f=open(folder+'/'+fname,'wb')
            f.write(video)
            f.close()
'''
"""