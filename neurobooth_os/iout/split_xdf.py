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
import h5io
import json


def compute_clocks_diff() -> float:
    """
    Compute difference between local LSL and Unix clock.
    :returns: The offset between the clocks (in seconds).
    """
    return time.time() - pylsl.local_clock()


def split_sens_files(
    xdf_path: str,
    log_task_id: str,
    task_id: str,
    conn,
) -> List[str]:
    """Split an XDF file into multiple HDF5 files (one per sensor).
    Also contains logic for logging expected files to the database.

    :param xdf_path: Full path to the XDF file.
    :param log_task_id: Task log ID for the database.
    :param task_id: Task ID for the database (and to specify which files to split).
    :param conn: Connection to the database.
    :returns: The list of HDF5 files generated by the split.
    """
    # We import this here so that it is not a dependency for the external split_xdf script.
    from neurobooth_os.iout import metadator as meta

    device_data = parse_xdf(xdf_path, meta.get_device_ids(task_id))
    write_device_hdf5(device_data)
    log_to_database(device_data, conn, log_task_id)
    return [d.hdf5_path for d in device_data]


class DeviceData(NamedTuple):
    device_id: str
    device_data: Any
    marker_data: Any
    video_files: List[str]
    sensor_ids: List[str]
    hdf5_path: str


def parse_xdf(xdf_path: str, device_ids: Optional[List[str]] = None) -> List[DeviceData]:
    """
    Split an XDF file into device/stream-specific HDF5 files.

    :param xdf_path: The path to the XDF file to parse.
    :param device_ids: If provided, only parse files corresponding to the specified devices.
    :returns: A structured representation of information extracted from the XDF file for each device.
    """
    data, _ = pyxdf.load_xdf(xdf_path, dejitter_timestamps=False)

    # Find marker stream to associate with each device
    marker = [d for d in data if d["info"]["name"] == ["Marker"]][0]

    # Get video file names for each device "videofiles" marker is present
    video_files = {}
    if "videofiles" in [d["info"]["name"][0] for d in data]:
        video_data = [v for v in data if v["info"]["name"] == ["videofiles"]]
        # Video file marker format is ["streamName, fname.mov"]
        for d in video_data[0]["time_series"]:
            if d[0] == "":
                continue
            stream_id, file_id = d[0].split(",")
            if stream_id in video_files:
                video_files[stream_id].append(file_id)
            else:
                video_files[stream_id] = [file_id]

    # Parse device data into more structured format; associate with marker and videos
    results = []
    for device_data in data:
        device_name = device_data["info"]["name"][0]

        # Exclude streams are associated with other devices and not represented by their own HDF5 file
        if device_name in ["Marker", "videofiles"]:
            continue

        device_id = device_data["info"]["desc"][0]["device_id"][0]
        sensor_id_str = device_data["info"]["desc"][0]["sensor_ids"][0]
        sensor_ids = json.loads(sensor_id_str.replace("'", '"'))  # Deserialize into list

        if (device_ids is not None) and (device_id not in device_ids):  # Only split specified devices
            continue

        results.append(DeviceData(
            device_id=device_id,
            device_data=device_data,
            marker_data=marker,
            video_files=video_files[device_name] if device_name in video_files else [],
            sensor_ids=sensor_ids,
            hdf5_path=_make_hdf5_path(xdf_path, device_id, sensor_ids),
        ))

    return results


def _make_hdf5_path(xdf_path: str, device_id: str, sensor_ids: List[str]) -> str:
    """
    Generate a path for a device HDF5 file extracted from an XDF file.

    :param xdf_path: Full path to the XDF file.
    :param device_id: ID string for the device.
    :param sensor_ids: List of ID strings for each included sensor.
    :returns: A standardized file name for corresponding device HDF5 file.
    """
    sensor_list = "-".join(sensor_ids)
    head, _ = op.splitext(xdf_path)
    return f"{head}-{device_id}-{sensor_list}.hdf5"


def write_device_hdf5(device_data: List[DeviceData]) -> None:
    """
    Write the HDF5 files containing extracted device data.
    :param device_data: A list of objects containing the extracted device information.
    """
    for dev in device_data:
        data_to_write = {"marker": dev.marker_data, "device_data": dev.device_data}
        h5io.write_hdf5(dev.hdf5_path, data_to_write, overwrite=True)


LOG_SENSOR_COLUMNS = [
    "log_task_id",
    "true_temporal_resolution",
    "true_spatial_resolution",
    "file_start_time",
    "file_end_time",
    "device_id",
    "sensor_id",
    "sensor_file_path",
]


def log_to_database(
        device_data: List[DeviceData],
        conn,
        log_task_id: str,
) -> None:
    """
    Log the names of sensor data files to the database.
    :param device_data: A list of objects containing the extracted device information.
    :param conn: A database connection object.
    :param log_task_id: The value to insert into the log_task_id column.
    """
    # We import this here so that it is not a dependency for the external split_xdf script.
    from neurobooth_terra import Table
    table_sens_log = Table("log_sensor_file", conn=conn)

    for dev in device_data:
        # Calculate timing characteristics of the data stream
        time_offset = compute_clocks_diff()
        timestamps = dev.device_data["time_stamps"]
        start_time = datetime.fromtimestamp(timestamps[0] + time_offset).strftime("%Y-%m-%d %H:%M:%S")
        end_time = datetime.fromtimestamp(timestamps[-1] + time_offset).strftime("%Y-%m-%d %H:%M:%S")
        temporal_resolution = 1 / np.median(np.diff(timestamps))

        # Construct the set of file names associated with the sensor
        hdf5_folder, hdf5_file = os.path.split(dev.hdf5_path)
        sensor_file_paths = [hdf5_file, *dev.video_files]
        # File paths need to start with the session folder for downstream scripts
        _, session_folder = os.path.split(hdf5_folder)
        sensor_file_paths = [f'{session_folder}/{f}' for f in sensor_file_paths]
        # Covert to array string for postgres
        sensor_file_paths = '{' + ', '.join(sensor_file_paths) + '}'

        for sensor_id in dev.sensor_ids:
            vals = [(
                log_task_id,
                temporal_resolution,
                None,
                start_time,
                end_time,
                dev.device_id,
                sensor_id,
                sensor_file_paths,
            )]
            table_sens_log.insert_rows(vals, LOG_SENSOR_COLUMNS)


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


def postpone_xdf_split(
    xdf_path: str,
    task_id: str,
    log_task_id: str,
    backlog_file: str,
) -> None:
    """ Update the backlog file to indicate that the given XDF should be split during post-processing.
    :param xdf_path: Full path to the XDF file.
    :param task_id: Task ID to specify which sensor files should be split out.
    :param log_task_id: Task log ID for the database.
    :param backlog_file: The file keeping track of which XDFs need to be split.
    """
    with open(backlog_file, "a+") as f:
        f.write(f"{xdf_path},{task_id},{log_task_id}\n")


def postprocess_xdf_split(
        backlog_file: str,
        conn,
) -> None:
    """
    Split all XDFs in the backlog file.
    :param backlog_file: The file keeping track of which XDFs need to be split.
    :param conn: Connection to the database.\
    """
    import sys
    import csv
    import neurobooth_os.log_manager as log_mgr

    # Read file and split to HDF5 in the same directory
    incomplete = []
    with open(backlog_file, newline="") as csvfile:
        for row in csv.reader(csvfile, delimiter=",", quotechar="|"):
            xdf_path, task_id, log_task_id = row
            try:
                split_sens_files(xdf_path, log_task_id, task_id, conn)
            except:
                incomplete.append(row)
                if log_mgr.APP_LOGGER is not None:
                    log_mgr.APP_LOGGER.error(f'Unable to process: {xdf_path}', exc_info=sys.exc_info())

    # Processing complete; clear out the backlog file
    with open(backlog_file, "w") as f:
        f.write("")
        for row in incomplete:
            f.write(",".join(row) + '\n')
