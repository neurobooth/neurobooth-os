# -*- coding: utf-8 -*-
"""
Created on Mon May 16 17:11:41 2022

@author: ACQ
"""

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


def get_frames_mean_rgb(vid, folder_out, cam_n=1):

    t0 = time.time()

    head, base_name = op.split(vid)
    fname_hdf5 = glob.glob(f"{head}/{base_name[:30]}*Intel_D455_{cam_n}*.hdf5")

    if not fname_hdf5:
        print(f"NO HDF5 found for {base_name}. Skipping")
        return
    elif len(fname_hdf5) > 1:
        print(
            f"MULTIPLE HDF5 found for {base_name}. Taking {fname_hdf5[0]} instead of {fname_hdf5[1:]}"
        )

    fname_hdf5 = fname_hdf5[0]
    head, fname = op.split(fname_hdf5.replace(".hdf5", "_RGB_frame_means.hdf5"))
    _, sess_fold = op.split(head)
    fold_out = op.join(folder_out, sess_fold)
    fname_out = op.join(fold_out, fname)

    if op.exists(fname_out):
        return

    if not op.exists(fold_out):
        os.mkdir(fold_out)

    lsl_data = read_hdf5(fname_hdf5)
    n_lslframes = lsl_data["device_data"]["time_series"].shape[0]
    first_frame_lsl = lsl_data["device_data"]["time_series"][0, 1]
    last_frame_lsl = lsl_data["device_data"]["time_series"][-1, 1]
    lsl_dev_data = lsl_data["device_data"]["time_series"]
    intel_lsl = lsl_data["device_data"]
    fps_depth = int(intel_lsl["info"]["desc"][0]["fps_depth"][0])
    fps_rgb = int(intel_lsl["info"]["desc"][0]["fps_rgb"][0])
    size_depth = eval(intel_lsl["info"]["desc"][0]["size_depth"][0])
    size_rgb = eval(intel_lsl["info"]["desc"][0]["size_rgb"][0])

    # plt.plot(np.diff(lsl_data['device_data']['time_series'][:,1]))

    _, fname = op.split(vid.replace(".bag", ".avi"))

    video_filename = op.join(fold_out, fname)

    if not op.exists(video_filename):
        n_frames, frame_ix = convert_bag_2_avi(
            video_filename, vid, fps_rgb, size_rgb, fps_depth, size_depth
        )

        print(
            f"video n frames: {n_frames}, lsl frames {last_frame_lsl - first_frame_lsl +1}, len lsl data {n_lslframes}"
        )
        print(f"first_frame_lsl: {first_frame_lsl}, last_frame_lsl {last_frame_lsl }")

    cap = cv2.VideoCapture(video_filename)
    fps = cap.get(5)
    new_fps = 60

    decimation = round(fps / new_fps)

    frame_means = np.zeros((lsl_dev_data.shape[0], 3))
    frame_means[:, :] = np.nan
    frame_n = -1
    frame_inxs = []

    success = True
    while success:
        success, img = cap.read()
        if not success:
            break

        frame_n += 1
        if frame_n % decimation:
            continue

        rgb_m = img.mean(0).mean(0)

        inx = np.where(lsl_dev_data[:, 1].astype(int) == frame_ix[frame_n])

        if len(inx[0]) > 1:
            print(f"more than one frame n {frame_n}, bag index {frame_ix[frame_n]}")

        elif len(inx[0]) == 0:
            print(f"no match for frame n {frame_n}, bag index {frame_ix[frame_n]}")
            continue

        frame_means[inx[0]] = rgb_m
        frame_inxs.append(frame_n)

    assert len(frame_inxs)

    lsl_data["device_data"]["time_series"] = frame_means

    assert len(lsl_data["device_data"]["time_stamps"]) == len(
        lsl_data["device_data"]["time_series"]
    )

    lsl_data["device_data"]["info"]["nominal_srate"] = new_fps
    lsl_data["device_data"]["info"]["name"] = "RGB frame mean"

    write_hdf5(fname_out, lsl_data, overwrite=True)
    print(
        f"Done {vid} with {len(lsl_data['device_data']['time_series'])} frames in {(time.time() - t0):.2f}"
    )


def convert_bag_2_avi(
    video_filename, fname_bag, fps_rgb, size_rgb, fps_depth, size_depth
):

    # Configure depth and color streams
    pipeline = rs.pipeline()
    config = rs.config()
    # load bag data
    rs.config.enable_device_from_file(config, fname_bag, repeat_playback=False)
    # config.enable_stream(rs.stream.depth, rs.format.z16, fps_depth)
    config.enable_stream(rs.stream.color, rs.format.rgb8, fps_rgb)

    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    # Create opencv window to render image in
    video_out = cv2.VideoWriter(video_filename, fourcc, fps_rgb, size_rgb)

    # Create colorizer object
    # colorizer = rs.colorizer()
    align = rs.align(rs.stream.color)

    pipeline_profile = pipeline.start(config)
    playback = pipeline_profile.get_device().as_playback().set_real_time(False)

    ix = 0
    frame_ix = []
    # Streaming loop
    while True:
        # Get frameset of depth
        try:
            frames = pipeline.wait_for_frames()
        except RuntimeError:
            break
        frame_ix.append(frames.get_frame_number())

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

    print(f"finished {os.path.basename(fname_bag)}")
    return ix, frame_ix


if __name__ == "__main__":
    import datetime

    t0 = datetime.datetime.now()

    folder_in = "Z:/data"
    folder_out = "Z:/processed_data"

    for cam_n in range(1, 4):
        vids = glob.glob(op.join(folder_in, "*", f"*timing_test_obs_intel{cam_n}.bag"))
        for vid in vids:
            try:
                get_frames_mean_rgb(vid, folder_out, cam_n)
            except:
                print(f"no good {vid}")
    print(f"total time: {datetime.datetime.now() - t0}")
