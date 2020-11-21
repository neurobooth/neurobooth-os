import cv2
from pylsl import StreamInfo, StreamOutlet
import threading

WC_WIDTH = 640
WC_HEIGHT = 480
WC_CHNS = 1
SAMPLE_RATE = 90



vc = cv2.VideoCapture(0)
fourcc = cv2.VideoWriter_fourcc('M','J','P','G')
vc.set(cv2.CAP_PROP_FPS, SAMPLE_RATE)
vc.set(cv2.CAP_PROP_FRAME_HEIGHT, WC_HEIGHT)
vc.set(cv2.CAP_PROP_FRAME_WIDTH, WC_WIDTH)
vc.set(cv2.CAP_PROP_FOURCC, fourcc)
vc.set(cv2.CAP_PROP_FPS, SAMPLE_RATE)


stream_info_webcam = StreamInfo('Webcam', 'Experiment', WC_WIDTH * WC_HEIGHT * WC_CHNS, SAMPLE_RATE, 'int16', 'webcamid_4')
outlet_webcam = StreamOutlet(stream_info_webcam)


def record():
    while True:
        rval, frame = vc.read()
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        outlet_webcam.push_sample(frame.flatten())



threading.Thread(target=record).start()