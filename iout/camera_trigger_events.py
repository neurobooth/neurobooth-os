import os
import sys
import threading
import uuid
import cv2
from pylsl import StreamInfo, StreamOutlet
class ViedoCapture():
    recording = False
    def __init__(self, cam_dict):
        self.cap = []
        self.writers = []
        self.outlets = []
        self.frameCounter = 1
        self.recording = False
        self.showUI = False
        self.winNames = []
        self.cam_dict = cam_dict
    def init(self, filepath, description):
        self.filepath = filepath
        ## creates the settings; creates the stream
        for cam in self.cam_dict:
            filename = description + '_' + cam['name'] + '.avi'
            cap_i = cv2.VideoCapture(cam['index'])
            if not cap_i.isOpened():
                continue
            self.cap.append(cap_i)
            # Ui-Information
            if self.showUI:
                winName = 'Camera ' + str(cam['index'])
                self.winNames.append(winName)
                cv2.namedWindow(winName)
            cap_i.set(cv2.CAP_PROP_FPS, 90)
            cap_i.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap_i.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            fps = cap_i.get(cv2.CAP_PROP_FPS)
            width = cap_i.get(cv2.CAP_PROP_FRAME_WIDTH)
            height = cap_i.get(cv2.CAP_PROP_FRAME_HEIGHT)
            filename = os.path.join(self.filepath, filename)
            fourcc = cv2.VideoWriter_fourcc('M','J','P','G')
            writer_i = cv2.VideoWriter(filename, fourcc, fps, (int(width), int(height)))
            self.writers.append(writer_i)
            self.outlets.append(self.createOutlet(cam['index'], filename, cam['name']))
            print('width:' + str(width) + ' height:' + str(height) + 'fps:' + str(fps))
        # print('setup Cameras')
    def capture(self):
        self.recording = True
        try:
            while self.recording:
                for i, cap_i in enumerate(self.cap):
                    ret, frame = cap_i.read()
                    if self.showUI:
                        win_i = self.winNames[i]
                        cv2.imshow(win_i, frame)
                    self.outlets[i].push_sample([self.frameCounter])
                    self.writers[i].write(frame)
                self.frameCounter += 1
                cv2.waitKey(1)
        finally:
            print('capturwegabrsdf')
    def stopRecording(self):
        self.recording = False
        for cap_i in self.cap:
            cap_i.release()
        cv2.destroyAllWindows()
    def createOutlet(self, index, filename,cam_name):
        streamName = 'VideoFrameMarker' + cam_name
        info = StreamInfo(name=streamName, type='videostream', channel_format='float32', channel_count=1,
                          source_id=str(uuid.uuid4()))
        videoFile = filename
        if sys.platform == "linux":
            videoFile = os.path.splitext(filename)[0] + '.ogv'
        info.desc().append_child_value("videoFile", videoFile)
        return StreamOutlet(info)
if __name__ == "__main__":
    cam_dict = [{'name': 'cam_0', 'index': 0}]
    record_dir = r'C:\git\neurobooth-eel'
    participant='Montag'
    videocapture = ViedoCapture(cam_dict)
    videocapture.init(record_dir, participant)
    ##self.videocapture.stopRecording()
    cap = threading.Thread(target=videocapture.capture)
    cap.start()