import logging
import os
from typing import Dict

import cv2
import numpy as np
import yaml

from neurobooth_os.log_manager import make_db_logger
from neurobooth_os import config


def _read_bytes_to_avi(images_filename: str, video_out: cv2.VideoWriter, height, width, depth) -> None:
    """
    Reads the file containing the raw images and produces an AVI file encoded as MJPEG
    Parameters
    ----------
    images_filename  Name of file used to store the row frame data
    video_out        CV2 video writer
    height           frame height in pixels
    width            frame depth in pixels
    depth            frame depth

    Returns
    -------
    None
    """
    with open(images_filename, "rb") as f:
        byte_size = height * width * depth
        while True:
            chunk = f.read(byte_size)
            if chunk:
                bytes_1d = np.frombuffer(chunk, dtype=np.uint8)
                frame = np.reshape(bytes_1d, newshape=(height, width, depth))
                video_out.write(frame)
            else:
                return


def run_conversion() -> None:
    """
    Runs raw image file to AVI conversion for all image files in the local_data_dir specified in config file

    Returns
    -------
    None
    """

    config.load_config()
    logger = make_db_logger()
    data_folder = config.neurobooth_config.acquisition.local_data_dir
    subfolders = [f.path for f in os.scandir(data_folder) if f.is_dir()]

    try:
        for folder in subfolders:
            logger.info(f'FLIR: Starting conversion in {folder}')
            manifests = []
            for file in os.listdir(folder):
                if file.endswith("flir_manifest.yaml"):
                    manifests.append(os.path.join(folder, file))

            for manifest_filename in manifests:
                with open(manifest_filename, 'r') as file:
                    manifest: Dict = yaml.safe_load(file)
                    image_filename = manifest["image_file"]
                    if os.path.exists(image_filename):

                        vid_width = manifest['frame_width']
                        vid_height = manifest['frame_height']
                        vid_depth = manifest['frame_depth']
                        frame_rate_out = manifest['frame_rate']

                        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
                        frame_size = (vid_width, vid_height)  # images size in pixels

                        video_filename = image_filename.replace(".images", ".avi")
                        video_out = cv2.VideoWriter(
                            video_filename, fourcc, frame_rate_out, frame_size
                        )
                        _read_bytes_to_avi(image_filename, video_out, vid_height, vid_width, vid_depth)
                        video_out.release()
                        if os.path.exists(video_filename):
                            os.remove(image_filename)
                            if os.path.exists(manifest_filename):
                                file.close()
                                os.remove(manifest_filename)

                        # logger.info(f'FLIR: Finished conversion of {image_filename}')
                    else:
                        logger.error(f"Flir images file not found {image_filename}")
            logger.info(f'FLIR: Finished conversion in {folder}')
    finally:
        logging.shutdown()


if __name__ == "__main__":
    run_conversion()
