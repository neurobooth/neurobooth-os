# -*- coding: utf-8 -*-
"""
Created on Fri Jul 22 14:30:52 2022

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
import pandas as pd

import matplotlib.pyplot as plt


def convert_bag_vid_tstams(fname_vid, fname_hdf5, folder_out):

    head, fname = op.split(fname_hdf5.replace(".hdf5", "_frameTstamps.csv"))
    _, sess_fold = op.split(head)
    fold_out = op.join(folder_out, sess_fold)
    fname_out = op.join(fold_out, fname)

    if not op.exists(fold_out):
        os.mkdir(fold_out)

    lsl_data = read_hdf5(fname_hdf5)

    intel_lsl = lsl_data["device_data"]
    fps_depth = int(intel_lsl["info"]["desc"][0]["fps_depth"][0])
    fps_rgb = int(intel_lsl["info"]["desc"][0]["fps_rgb"][0])
    size_depth = eval(intel_lsl["info"]["desc"][0]["size_depth"][0])
    size_rgb = eval(intel_lsl["info"]["desc"][0]["size_rgb"][0])

    _, fname = op.split(fname_vid.replace(".bag", ".avi"))
    video_filename = op.join(fold_out, fname)

    # Configure depth and color streams
    pipeline = rs.pipeline()
    config = rs.config()
    # load bag data
    rs.config.enable_device_from_file(config, fname_vid, repeat_playback=False)
    # config.enable_stream(rs.stream.depth, rs.format.z16, fps_depth)
    config.enable_stream(rs.stream.color, rs.format.rgb8, fps_rgb)

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    # Create opencv window to render image in
    video_out = cv2.VideoWriter(video_filename, fourcc, fps_rgb, size_rgb)

    # Create colorizer object
    # colorizer = rs.colorizer()
    align = rs.align(rs.stream.color)

    pipeline.start(config)
    tstamsp = []
    ix = 0
    frame_ix = []
    # Streaming loop
    while True:
        # Get frameset of depth
        try:
            frames = pipeline.wait_for_frames()
            tstamp = frames.get_timestamp()
            tstamsp.append(tstamp)
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

        ix += 1
        if not ix % 100:
            print(".", end="")

    video_out.release()
    pipeline.stop()

    df = pd.DataFrame({"frame_ix": frame_ix, "timestamp": tstamsp})
    df.to_csv(fname_out, index=False)

    return frame_ix


if __name__ == "__main__":
    import datetime

    t0 = datetime.datetime.now()

    folder_in = "Z:/data"
    folder_out = "Z:/processed_data"

    for cam_n in range(1, 4):
        vids = glob.glob(op.join(folder_in, "*", f"*timing_test_obs_intel{cam_n}.bag"))
        for fname_vid in vids:
            try:
                head, base_name = op.split(fname_vid)
                fname_hdf5 = glob.glob(
                    f"{head}/{base_name[:30]}*Intel_D455_{cam_n}*.hdf5"
                )
                fname_hdf5 = fname_hdf5[0]
                convert_bag_vid_tstams(fname_vid, fname_hdf5, folder_out)

                frame_ix = convert_bag_vid_tstams(fname_vid, fname_hdf5, folder_out)

                # CHECK IF NO mised frames while reading the file, do it again if misses
                if sum(np.diff(frame_ix) > 1):
                    misses = sum(np.diff(frame_ix) > 1)
                    print(
                        fname_vid,
                        "\n\tmissed frames while reading bag file",
                        misses,
                        "frames",
                    )
                    frame_ix = convert_bag_vid_tstams(fname_vid, fname_hdf5, folder_out)

            except Exception as e:
                print(f"no good {fname_vid}, {e}")

    print(f"total time: {datetime.datetime.now() - t0}")
