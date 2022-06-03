# -*- coding: utf-8 -*-
"""
Created on Wed Apr 20 13:14:32 2022

@author: ACQ
"""

import os
import os.path as op
import numpy as np
import cv2
import mediapipe as mp
import time
import glob
import pyrealsense2 as rs
from h5io import read_hdf5, write_hdf5


class BodyLandMarks():
    def __init__(self, staticMode=False,model_complexity=2, enable_segmentation=False, min_detection_confidence=0.5):
        self.staticMode = staticMode
        self.model_complexity = model_complexity
        self.enable_segmentation = enable_segmentation
        self.min_detection_confidence = min_detection_confidence

        self.mpDraw = mp.solutions.drawing_utils
        self.mpPose = mp.solutions.pose
        self.Pose = self.mpPose.Pose(self.staticMode, 
                                     model_complexity=self.model_complexity,
                                     enable_segmentation = self.enable_segmentation,
                                                 
                                                 min_detection_confidence=self.min_detection_confidence,
                                                 )

        self.drawSpec = self.mpDraw.DrawingSpec(thickness=1, circle_radius=1)

    def findBodyLandmark(self, img, draw=True):
        self.imgRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        self.results = self.Pose.process(self.imgRGB)

        points = []

        if self.results.pose_landmarks:
            for lmk in self.results.pose_landmarks.landmark:
                if draw:
                    self.mpDraw.draw_landmarks(img, lmk, self.mpPose.POSE_CONNECTIONS, self.drawSpec, self.drawSpec)

                point = []
                for id, lm in enumerate(self.results.pose_landmarks.landmark):
                    # print(lm)
                    ih, iw, ic = img.shape
                    x, y = int(lm.x * iw), int(lm.y * ih)
                    #cv2.putText(img, str(id), (x,y), cv2.FONT_HERSHEY_SIMPLEX, 0.3, (0,255,0), 1)
                    #print(id, x, y)
                    point.append([x,y])
                points.append(point)
        return img, points

    
def get_body_landmarks(vid, folder_out, cam_n=1):
    
    t0 = time.time()
    
    head, base_name = op.split(vid)
    fname_hdf5 = glob.glob(f'{head}/{base_name[:30]}*Intel_D455_{cam_n}*.hdf5')
    
    if not fname_hdf5:
        print(f"NO HDF5 found for {base_name}. Skipping")
        return
    elif len(fname_hdf5)>1:
        print(f"MULTIPLE HDF5 found for {base_name}. Taking {fname_hdf5[0]} instead of {fname_hdf5[1:]}")
    
    fname_hdf5 = fname_hdf5[0]
    head, fname =  op.split(fname_hdf5.replace('.hdf5', '_body_landmarks.hdf5'))
    _, sess_fold = op.split(head)
    fold_out = op.join(folder_out, sess_fold)
    fname_out = op.join(fold_out, fname)
    
    if op.exists(fname_out):
        return
    
    if not op.exists(fold_out):
        os.mkdir(fold_out)
    
    lsl_data = read_hdf5(fname_hdf5)
    n_lslframes = lsl_data['device_data']['time_series'].shape[0]
    if n_lslframes < 2:
        return
    first_frame_lsl = lsl_data['device_data']['time_series'][0,1]
    last_frame_lsl = lsl_data['device_data']['time_series'][-1,1]
    lsl_dev_data = lsl_data['device_data']['time_series']
    intel_lsl = lsl_data['device_data']
    fps_depth = int(intel_lsl['info']['desc'][0]['fps_depth'][0])
    fps_rgb = int(intel_lsl['info']['desc'][0]['fps_rgb'][0])
    size_depth = eval(intel_lsl['info']['desc'][0]['size_depth'][0])
    size_rgb = eval(intel_lsl['info']['desc'][0]['size_rgb'][0])
    
    # plt.plot(np.diff(lsl_data['device_data']['time_series'][:,1]))
    
    _, fname =  op.split(vid.replace(".bag", ".avi"))
        
    video_filename = op.join(fold_out, fname)
    
    try:
        n_frames, frame_ix = convert_bag_2_avi(video_filename, vid, fps_rgb, size_rgb, fps_depth, size_depth)
    except RuntimeError:
        print(f"runtime error for {video_filename}")
        return
    
    print(f"video n frames: {n_frames}, lsl frames {last_frame_lsl - first_frame_lsl +1}, len lsl data {n_lslframes}")
    print(f"first_frame_lsl: {first_frame_lsl}, last_frame_lsl {last_frame_lsl }")
    
    cap = cv2.VideoCapture(video_filename)
    fps = cap.get(5)
    new_fps = 60

    decimation = round(fps/new_fps)

    detector = BodyLandMarks()
    
    frame_n = -1
    frame_inxs, ts = [], []
    success = True
    while success:
        success, img = cap.read()
        if not success:
            break

        frame_n += 1
        if frame_n % decimation:
            continue

        img, ppoints = detector.findBodyLandmark(img, draw=False)
        if len(ppoints)!=0:
            points = ppoints[0]
            points = np.stack(points)
        else:
            points = np.zeros((33,2))
            # print(f"empty {frame_n} in {vid}")
        
        # map bag frame number to lsl data
        inx =  np.where(lsl_dev_data[:,1] == frame_ix[frame_n])        
        if len(inx[0])> 1:
            # print(f"more than one frame n {frame_n}, bag index {frame_ix[frame_n]}")   
            pass
        elif len(inx[0]) == 0:
            # print(f"no match for frame n {frame_n}, bag index {frame_ix[frame_n]}")
            continue
        
        ts.append(points)
        frame_inxs.append(inx[0][0])

    assert(len(frame_inxs))

    tts = np.stack(ts)

    
    lsl_data['device_data']['time_stamps'] = lsl_data['device_data']['time_stamps'][frame_inxs]
    lsl_data['device_data']['time_series'] = tts
    
    assert(len(lsl_data['device_data']['time_stamps']) == len(lsl_data['device_data']['time_series']))

    lsl_data['device_data']['info']['nominal_srate'] = new_fps
    lsl_data['device_data']['info']['name'] = 'mediapipe body landmarks'

    
    write_hdf5(fname_out, lsl_data, overwrite=True)
    print(f"Done {vid} with {len(lsl_data['device_data']['time_series'])} frames in {(time.time() - t0):.2f}")


def convert_bag_2_avi(video_filename, fname_bag, fps_rgb, size_rgb, fps_depth, size_depth):
    
    # Configure depth and color streams
    pipeline = rs.pipeline()
    config = rs.config()
    # load bag data
    rs.config.enable_device_from_file(config, fname_bag, repeat_playback=False)
    config.enable_stream(rs.stream.depth, rs.format.z16, fps_depth)
    config.enable_stream(rs.stream.color, rs.format.rgb8, fps_rgb)

    pipeline.start(config)


    fourcc = cv2.VideoWriter_fourcc( *'MJPG')
    # Create opencv window to render image in
    video_out = cv2.VideoWriter(video_filename, fourcc, fps_rgb, size_rgb)

    # Create colorizer object
    # colorizer = rs.colorizer()
    align = rs.align(rs.stream.color)

    ix = 0
    frame_ix = []
    # Streaming loop
    while True:
        # Get frameset of depth
        try:
            frames = pipeline.wait_for_frames(timeout_ms=1000)
            frame_ix.append(frames.get_frame_number())
        except RuntimeError:
            break

        # Align the depth frame to color frame
        aligned_frames = align.process(frames)

        # Get aligned frames
        # aligned_depth_frame = aligned_frames.get_depth_frame()
        color_frame = aligned_frames.get_color_frame()
        # depth_frame_col = colorizer.colorize(aligned_depth_frame)
        # depth_image = np.asanyarray(depth_frame_col.get_data())

        color_image = np.asanyarray(color_frame.get_data())
        color_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2RGB)
        video_out.write(color_image)

        ix +=1
        if not ix%100: print(".", end ="")

    video_out.release()

    print(f"finished {os.path.basename(fname_bag)}")
    return ix, frame_ix
    
    
if __name__ == '__main__':
    import datetime 
    
    t0 = datetime.datetime.now()
    
    exclude =[ "calibration_obs", 'old']
    folder_in =  'Z:/data'
    folder_out = 'Z:/processed_data'
    vids = glob.glob(op.join(folder_in, "*", "*_intel1.bag"))
    for vid in vids:        
        if any([e in vid for e in exclude]):
            continue
        
        get_body_landmarks(vid, folder_out)
    
    print(f"total time: {datetime.datetime.now() - t0}")


