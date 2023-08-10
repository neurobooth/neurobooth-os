import os
import pyxdf
import pylsl
import liesl
import time
import numpy as np
import os.path as op
from datetime import datetime
from pathlib import Path
from typing import NamedTuple, Optional, Any, List
import psycopg2

from h5io import write_hdf5

from neurobooth_os.iout import metadator as meta
from neurobooth_terra import Table
from neurobooth_os.config import neurobooth_config, get_server_name_from_env


def compute_clocks_diff() -> float:
    """
    Compute difference between local LSL and Unix clock.
    :returns: The offset between the clocks (in seconds).
    """

    time_local = pylsl.local_clock()
    time_ux = time.time()
    time_offset = time_ux - time_local
    return time_offset


# TODO: Refactor into parse XDF, (Future: correct device metadata), write hdf5s, log to DB
def split_sens_files(
    fname,
    log_task_id=None,
    task_id=None,
    conn=None,
    folder="",
    dont_split_xdf_fpath=None
):
    """Split xdf file per sensor

    Parameters
    ----------
    fname : str
        name of the file to split
    log_task_id : str, optional
        task log id for the database, by default None. If conn not None, it can not be None.
    task_id : str, optional
        task id for the database, by default None. If conn not None, it can not be None.
    conn : callable
        Connector to the database, if None does not insert rows, by default None
    folder : str
        path to fname
    Returns
    -------
    files : list
        list of files for each stream
    """

    t0 = time.time()
    # Read xdf file
    data, header = pyxdf.load_xdf(fname, dejitter_timestamps=False)

    # Find marker stream to add in to each h5 file
    marker = [d for d in data if d["info"]["name"] == ["Marker"]]

    if conn is not None:
        table_sens_log = Table("log_sensor_file", conn=conn)
        _, devices_ids, _, _ = meta._get_task_param(task_id, conn)

    # get video filenames if videofiles marker present
    videofiles = {}
    if "videofiles" in [d["info"]["name"][0] for d in data]:
        vid_data = [v for v in data if v["info"]["name"] == ["videofiles"]]
        # video file marker format is ["streamName, fname.mov"]
        for d in vid_data[0]["time_series"]:
            if d[0] == "":
                continue
            stream_id, file_id = d[0].split(",")
            if len(folder):
                file_id = f"{folder}/{file_id}"
            if videofiles.get(stream_id) is not None:
                videofiles[stream_id] += f", {file_id}"
            else:
                videofiles[stream_id] = file_id

    if dont_split_xdf_fpath is not None:
        with open(os.path.join(dont_split_xdf_fpath, "split_tohdf5.csv"), "a+") as f:
            f.write(f"{fname},{task_id}\n")
    files = []
    # Loop over each sensor
    for dev_data in data:
        name = dev_data["info"]["name"][0]
        if name in ["Marker", "videofiles"]:
            continue

        device_id = dev_data["info"]["desc"][0]["device_id"][0]
        sensors_id = eval(dev_data["info"]["desc"][0]["sensor_ids"][0])

        # Only log and split devices in task DB
        if task_id is not None and device_id not in devices_ids:
            # print(f"Skipping {name} not in tech obs device list: {devices_ids}")
            continue

        sensors = "-".join(sensors_id)
        data_sens = {"marker": marker[0], "device_data": dev_data}
        head, ext = op.splitext(fname)
        fname_full = f"{head}-{device_id}-{sensors}.hdf5"

        if dont_split_xdf_fpath is None:
            write_hdf5(fname_full, data_sens, overwrite=True)

        # print(f"Saving stream {name} to {fname_full}")
        files.append(fname_full)
        _, head = op.split(fname_full)

        time_offset = compute_clocks_diff()
        start_time = dev_data["time_stamps"][0] + time_offset
        end_time = dev_data["time_stamps"][-1] + time_offset
        start_time = datetime.fromtimestamp(start_time).strftime("%Y-%m-%d %H:%M:%S")
        end_time = datetime.fromtimestamp(end_time).strftime("%Y-%m-%d %H:%M:%S")
        temp_res = 1 / np.median(np.diff(dev_data["time_stamps"]))

        if len(folder):
            head = f"{folder}/{head}"

        if videofiles.get(name):
            head = f"{head}, {videofiles.get(name)}"
            # print(f"Videofile name: {head}")

        if log_task_id is not None:
            for sens_id in sensors_id:
                cols = [
                    "log_task_id",
                    "true_temporal_resolution",
                    "true_spatial_resolution",
                    "file_start_time",
                    "file_end_time",
                    "device_id",
                    "sensor_id",
                    "sensor_file_path",
                ]
                vals = [
                    (
                        log_task_id,
                        temp_res,
                        None,
                        start_time,
                        end_time,
                        device_id,
                        sens_id,
                        "{" + head + "}",
                    )
                ]
                table_sens_log.insert_rows(vals, cols)
    print(f"SPLIT XDF {task_id} took: {time.time() - t0}")
    return files


class DeviceData(NamedTuple):
    device_id: str
    device_data: Any
    marker_data: Any
    video_files: Optional[str]
    sensor_ids: List[str]


def parse_xdf(file_path: str, device_ids: Optional[List[str]] = None) -> List[DeviceData]:
    """
    Split an XDF file into device/stream-specific HDF5 files.

    :param file_path: The path to the XDF file to parse.
    :param device_ids: If provided, only parse files corresponding to the specified devices.
    :returns: A structured representation of information extracted from the XDF file for each device.
    """
    folder, file_name = os.path.split(file_path)
    data, _ = pyxdf.load_xdf(file_path, dejitter_timestamps=False)

    # Find marker stream to associate with each device
    marker = [d for d in data if d["info"]["name"] == ["Marker"]]

    # Get video file names for each device "videofiles" marker is present
    video_files = {}
    if "videofiles" in [d["info"]["name"][0] for d in data]:
        video_data = [v for v in data if v["info"]["name"] == ["videofiles"]]
        # Video file marker format is ["streamName, fname.mov"]
        for d in video_data[0]["time_series"]:
            if d[0] == "":
                continue
            stream_id, file_id = d[0].split(",")
            if folder:
                file_id = f"{folder}/{file_id}"
            if stream_id in video_files:
                video_files[stream_id] += f", {file_id}"
            else:
                video_files[stream_id] = file_id

    # Parse device data into more structured format; associate with marker and videos
    results = []
    for device_data in data:
        device_name = device_data["info"]["name"][0]
        if device_name in ["Marker", "videofiles"]:
            continue

        device_id = device_data["info"]["desc"][0]["device_id"][0]
        sensors_ids = eval(device_data["info"]["desc"][0]["sensor_ids"][0])  # Dirty trick for converting into a list

        if (device_ids is not None) and (device_id not in device_ids):  # Only split specified devices
            continue

        # sensors = "-".join(sensors_ids)
        # head, _ = op.splitext(file_name)
        # hdf5_name = f"{head}-{device_id}-{sensors}.hdf5"
        # hdf5_path = f'{folder}/{hdf5_name}' if folder else hdf5_name

        results.append(DeviceData(
            device_id=device_id,
            device_data=device_data,
            marker_data=marker,
            video_files=video_files[device_name] if device_name in video_files else None,
            sensor_ids=sensors_ids,
        ))

    return results


# TODO: Implement write hdf


# TODO: Implement file logging


def get_xdf_name(session: liesl.Session, fname_prefix: str) -> str:
    """Get with most recent session XDF file name.

    :param session: The current liesl Session object. Or object with the session.folder attribute.
    :param fname_prefix: Prefix of the xdf file name.
    :returns: File name of the XDF file.
    """
    fname = session.folder / Path(fname_prefix + ".xdf")
    base_stem = fname.stem.split("_R")[0]
    count = 0
    for f in fname.parent.glob(fname.stem + "*.xdf"):
        base_stem, run_counter = f.stem.split("_R")
        count = max(int(run_counter), count)
    run_str = "_R{0:03d}".format(count)
    final_fname = str(fname.with_name(base_stem + run_str).with_suffix(".xdf"))
    return final_fname


def create_h5_from_csv(
        dont_split_xdf_fpath: str,
        conn: psycopg2.connection,
        server_name: Optional[str] = None
) -> None:
    """
    :param dont_split_xdf_fpath: Path to the CSV file containing filenames and task IDs.
    :param conn: Connection to the database.
    :param server_name: A string matching one of the servers defined in the neurobooth_config.json file.
        If None, the name will be determined from the Windows User Profile, if possible.
    """
    if server_name is None:
        server_name = get_server_name_from_env()
        if server_name is None:
            raise Exception("A server name is required if the Windows user is not in (CTR, ACQ, or STM)")

    lines_todo = []
    fname = os.path.join(dont_split_xdf_fpath, "split_tohdf5.csv")
    import csv

    # read file and split to hdf5 in the same directory
    with open(fname, newline="") as csvfile:
        lines = csv.reader(csvfile, delimiter=",", quotechar="|")

        for row in lines:
            # change to NAS path if necessary
            if not os.path.exists(row[0]):
                row[0] = row[0].replace(
                    neurobooth_config[server_name]["local_data_dir"][:-1],
                    neurobooth_config["remote_data_dir"]
                )
            out = split_sens_files(row[0], task_id=row[1], conn=conn)

            if len(out) == 0:
                lines_todo.append(row)

    # rewrite file in case some xdf didn't get split
    with open(fname, "w") as f:
        for lns in lines_todo:
            f.write(f"{lns[0]},{lns[1]}")
