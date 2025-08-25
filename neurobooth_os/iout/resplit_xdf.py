"""
This file splits an XDF file into constituent HDF5 files. It is meant to be called on the cluster without a full
installation of Neurobooth-OS.

new_path is where the processed_data will be saved. this is hardcoded - < if required can be moved and loaded from config>
"""

import os
import re
import argparse
import datetime
import importlib
import numpy as np
from typing import NamedTuple, List, Dict, Optional, Any, Callable, ClassVar
import h5io
import yaml
import psycopg2 as pg
from pydantic import BaseModel

import neurobooth_os.config as cfg

import neurobooth_os.iout.split_xdf as xdf


class SplitException(Exception):
    """For generic errors that occur when splitting an XDF file."""
    pass


class HDF5CorrectionSpec(BaseModel):
    marker: Optional[str] = None
    devices: Dict[str, str] = {}

    @staticmethod
    def load(path: str) -> 'HDF5CorrectionSpec':
        """
        Load the correction specification from a YAML configuration file.
        :param path: The path to the YAML file.
        :return: The correction specification.
        """
        try:
            with open(path, 'r') as stream:
                return HDF5CorrectionSpec(**yaml.safe_load(stream))
        except Exception as e:
            raise SplitException('Unable to load correction functions from {path}!') from e

    FUNC_STR_PATTERN: ClassVar = re.compile(r'(.*)\.py::(.*)\(\)')

    @staticmethod
    def import_function(func_str: str) -> Callable:
        """
        Import and return the function specified by a fully.qualified.module.py::func() string.
        This code is adapted from metadator, but we avoid the import because of dependency baggage.
        :param func_str: The string to parse and import.
        :return: The imported function.
        """
        match = re.match(HDF5CorrectionSpec.FUNC_STR_PATTERN, func_str)
        if match is None:
            raise SplitException(f'The function specification does not match the expected pattern: {func_str}')
        module, func = match.groups()

        try:
            module = importlib.import_module(module)
            return getattr(module, func)
        except Exception as e:
            raise SplitException(f'Unable to import {func_str}') from e

    def correct_device(self, device: xdf.DeviceData) -> xdf.DeviceData:
        """
        Apply in-memory corrections to device data if corrections were specified for the given device/marker.
        :param device: The device structure loaded from the XDF file.
        :return: The corrected device structure.
        """
        if self.marker is not None:
            func = HDF5CorrectionSpec.import_function(self.marker)
            device = func(device)

        device_id = device.device_id
        if device_id in self.devices:
            func = HDF5CorrectionSpec.import_function(self.devices[device_id])
            device = func(device)

        return device


XDF_NAME_PATTERN = re.compile(r'(\d+)_(\d\d\d\d-\d\d-\d\d)_\d\dh-\d\dm-\d\ds_(.*)_R001\.xdf', flags=re.IGNORECASE)


class XDFInfo(NamedTuple):
    """Structured representation of an XDF file name."""
    parent_dir: str
    name: str
    subject_id: str
    date: datetime.date
    task_id: str
    xdf_pathd: str

    @property
    def path(self) -> str:
        return os.path.join(self.parent_dir, self.name)

    @staticmethod
    def parse_xdf_name(xdf_path: str) -> 'XDFInfo':
        """
        Attempt to infer the subject ID, date, and task ID from the XDF file path.
        :param xdf_path: The path to the XDF file.
        :return: A structured representation of the XDF file name.
        """
        parent_dir, filename = os.path.split(xdf_path)
        match = re.match(XDF_NAME_PATTERN, filename)
        if match is None:
            raise SplitException(f'Unable to parse file name: {filename}')

        subject_id, date_str, task_id = match.groups()
        return XDFInfo(
            parent_dir=parent_dir,
            name=filename,
            subject_id=subject_id,
            date=datetime.date.fromisoformat(date_str),
            task_id=task_id,
            xdf_pathd=xdf_path,
        )


class DatabaseConnection:
    """Handles limited interactions with the Neurobooth database"""

    def __init__(self, config_path: str, tunnel: bool,override_host: Optional[str], override_port: Optional[int]):
        """
        Create a new DatabaseConnection based on the provided Neurobooth-OS configuration file.
        :param config_path: The path to the Neurobooth-OS configuration, including a 'database' entry.
        :param tunnel: Whether to SSH tunnel prior to connecting. Should be False if running on neurodoor.
        """
        self.connection = DatabaseConnection.connect(config_path, tunnel,override_host,override_port)

    @staticmethod
    def connect(config_path: str, tunnel: bool,override_host: Optional[str], override_port: Optional[int]) -> pg.extensions.connection:
        """
        Load and parse a Neurobooth-OS configuration, then create a psycopg2 connection.
        Note: This function copies some code from metadator.py, but importing that file introduces extra dependencies.

        :param config_path: The path to the Neurobooth-OS configuration, including a 'database' entry.
        :param tunnel: Whether to SSH tunnel prior to connecting. Should be False if running on neurodoor.
        """
        cfg.load_config(config_path, validate_paths=False)
        database_info = cfg.neurobooth_config.database

        if override_host:
            database_info.host = override_host
        if override_port:
            database_info.port = override_port

        # import logging
        # logging.basicConfig(
        # level=logging.DEBUG,  # Set to DEBUG for detailed logs
        # format='%(asctime)s %(levelname)s:%(name)s:%(message)s'
        # )
        # logger = logging.getLogger('sshtunnel_test')

        if tunnel:
            from sshtunnel import SSHTunnelForwarder
            # tunnel = SSHTunnelForwarder(
            #     ('neurodoor.nmr.mgh.harvard.edu', 22),
            #     ssh_username='dk028',
            #     # ssh_config_file=os.path.expanduser("/homes/9/dk028/.ssh/config"),
            #     ssh_pkey=os.path.expanduser("/homes/9/dk028/.ssh/id_rsa"),
            #     remote_bind_address=('neurodoor.nmr.mgh.harvard.edu', 5432),
            #     local_bind_address=("localhost", 6543)
            #     # logger=logger
            # )
            tunnel = SSHTunnelForwarder(
                database_info.remote_host,
                ssh_username=database_info.remote_user,
                ssh_config_file="~/.ssh/config",
                ssh_pkey="~/.ssh/id_rsa",
                remote_bind_address=(database_info.host, database_info.port),
                local_bind_address=("localhost", 6543),
            )
            # tunnel = sshtunnel.SSHTunnelForwarder(
            # ('neurodoor.nmr.mgh.harvard.edu', 22),  # Remote host and SSH port
            # ssh_username='dk028',             # Replace with your SSH username
            # ssh_pkey=os.path.expanduser("/homes/9/dk028/.ssh/id_rsa"),  # Path to your private key
            # remote_bind_address=('neurodoor.nmr.mgh.harvard.edu', 5432),       # Database host and port as seen from remote server
            # local_bind_address=("localhost", 6543),         # Local port
            # logger=logger
            # )

            print(f"Starting the tunnel with {database_info.remote_user} and {database_info.remote_host}")
            tunnel.start()
            host = tunnel.local_bind_host
            port = tunnel.local_bind_port
            print(f"Host and Port are {host} and {port}")
        else:
            host = database_info.host
            port = database_info.port

        return pg.connect(
            database=database_info.dbname,
            user=database_info.user,
            password=database_info.password,
            host=host,
            port=port,
        )

    DEVICE_ID_QUERY = """
    WITH device AS (
        -- This subquery defines a temporary table of log device IDs
        -- associated with the specified task and session.
        SELECT UNNEST(tparam.log_device_ids) AS log_device_id  -- Flatten the list
        -- We need to do a chain of joins to get from the session -> task -> task paramaters
        FROM log_session sess
        JOIN log_task task
            ON sess.log_session_id = task.log_session_id
        JOIN log_task_param tparam
            ON task.log_task_id = tparam.log_task_id
        -- Filter to just the session and task of interest.
        -- We use a parameterized query and pass in the filters to psycopg2.
        WHERE sess.subject_id = %(subject_id)s
            AND sess.date = %(session_date)s
            AND task.task_id = %(task_id)s
    )
    -- Now we can look up which devices were actually present during the task recording.
    SELECT dparam.device_id
    FROM device
    JOIN log_device_param dparam
        ON device.log_device_id = dparam.id
    """

    def get_device_ids(self, xdf_info: XDFInfo) -> List[str]:
        """
        Retrieve the list of device IDs associated with a given task and session.
        :param xdf_info: An XDF info structure, which details the task and session.
        :return: The list of device IDs retrieved from the log_* tables in the database.
        """
        query_params = {
            'subject_id': xdf_info.subject_id,
            'session_date': xdf_info.date.isoformat(),
            'task_id': xdf_info.task_id,
        }
        with self.connection.cursor() as cursor:
            cursor.execute(DatabaseConnection.DEVICE_ID_QUERY, query_params)
            return [row[0] for row in cursor.fetchall()]

    def log_split(self,xdf_info: XDFInfo, device_data: List[xdf.DeviceData]) -> None:
        """
        Create entries in the log_split table to reflect created HDF5 files.
        :param xdf_info: An XDF info structure, which details the task and session.
        :param device_data: Structures representing the XDF data for each device.
        """
        with self.connection.cursor() as cursor:
            for device in device_data:
                # The file path should be session/file.hdf5 to permit comparison to log_sensor_file
                time_offset = xdf.compute_clocks_diff()
                timestamps = device.device_data["time_stamps"]
                start_time = datetime.fromtimestamp(timestamps[0] + time_offset).strftime("%Y-%m-%d %H:%M:%S")
                end_time = datetime.fromtimestamp(timestamps[-1] + time_offset).strftime("%Y-%m-%d %H:%M:%S")
                temporal_resolution = 1 / np.median(np.diff(timestamps))
                hdf5_folder, hdf5_file = os.path.split(device.hdf5_path)
                _, session_folder = os.path.split(hdf5_folder)
                hdf5_file = f'{session_folder}/{hdf5_file}'

                _, session_folder = os.path.split(hdf5_folder)
                sensor_file_paths = [f'{session_folder}/{f}' for f in sensor_file_paths]
                # Covert to array string for postgres
                sensor_file_paths = '{' + ', '.join(sensor_file_paths) + '}'
    
                for sensor_id in device.sensor_ids:
                    query_params = {
                        'subject_id': xdf_info.subject_id,
                        'date': xdf_info.date.isoformat(),
                        'task_id': xdf_info.task_id,
                        'true_temporal_resolution': temporal_resolution,
                        'file_start_time': start_time,
                        'file_end_time': end_time,
                        'device_id': device.device_id,
                        'sensor_id': sensor_id,
                        'hdf5_file_path': hdf5_file,
                        'xdf_path': xdf_info.xdf_pathd,
                        'sensor_file_paths': sensor_file_paths,
                    }
                    cursor.execute(
                        """
                        INSERT INTO log_split (subject_id, date, task_id, temporal_resolution, start_time, end_time, device_id, sensor_id, hdf5_file_path,xdf_path,sensor_file_paths)
                        VALUES (%(subject_id)s, %(date)s, %(task_id)s, %(temporal_resolution)s, %(start_time)s, %(end_time)s , %(device_id)s, %(sensor_id)s, %(hdf5_file_path)s, %(xdf_path)s, %(sensor_file_paths)s)
                        """,
                        query_params
                    )
        self.connection.commit()


def device_id_from_yaml(file: str, task_id: str) -> List[str]:
    """
    Load a YAML file defining preset task ID -> device ID mappings and look up the given task.
    :param file: The YAML file containing the mappings.
    :param task_id: The task ID to look up.
    :return: The preset device IDs associated with the task ID.
    """
    try:
        with open(file, 'r') as stream:
            task_device_map = yaml.safe_load(stream)
        return task_device_map[task_id]
    except Exception as e:
        raise SplitException(f'Could not locate task {task_id} using map file {file}.') from e

def _remake_hdf5_path(xdf_path: str, device_id: str, sensor_ids: List[str]) -> str:
    """
    Generate a path for a device HDF5 file extracted from an XDF file.

    :param xdf_path: Full path to the XDF file.
    :param device_id: ID string for the device.
    :param sensor_ids: List of ID strings for each included sensor.
    :returns: A standardized file name for corresponding device HDF5 file.
    """
    sensor_list = "-".join(sensor_ids)
    head, _ = os.path.splitext(xdf_path)
    # new_path="/space/billnted/7/analyses/dk028/split_xdf_work/processed_data" #get this from somewhere
    new_path="/space/billnted/4/neurobooth/processed_data/"
    base_folder = os.path.basename(os.path.dirname(head)) # Extract the base folder directly
    directory_to_create = os.path.join(new_path, base_folder)
    new_file_path = os.path.join(directory_to_create, os.path.basename(head))
    if not os.path.exists(directory_to_create):
        os.makedirs(directory_to_create, exist_ok=True)
    return f"{new_file_path}-{device_id}-{sensor_list}.hdf5"
    # return f"{head}-{device_id}-{sensor_list}.hdf5"

def rewrite_device_hdf5(xdf_path: str,device_data: List[xdf.DeviceData]) -> List[xdf.DeviceData]:
    """
    Write the HDF5 files containing extracted device data.
    :param device_data: A list of objects containing the extracted device information.
    """
    new_device_data = []
    for dev in device_data:
        data_to_write = {"marker": dev.marker_data, "device_data": dev.device_data}
        new_hdf5_path = _remake_hdf5_path(xdf_path, dev.device_id, dev.sensor_ids)
        if os.path.exists(new_hdf5_path):
            print(f"HDF5 file {new_hdf5_path} already exists. Skipping writing for device {dev.device_id}.")
            # Optionally update the device object with the existing file path.
            # dev.hdf5_path = new_hdf5_path
            # new_device_data.append(dev)
            continue 

        new_dev = xdf.DeviceData(
            device_id=dev.device_id,
            device_data=dev.device_data,
            marker_data=dev.marker_data,
            video_files=dev.video_files,
            sensor_ids=dev.sensor_ids,
            hdf5_path=new_hdf5_path,  # Use the new path here
        )
        new_device_data.append(new_dev)
        h5io.write_hdf5(new_hdf5_path, data_to_write, overwrite=True)
    return new_device_data 

def split(
        xdf_path: str,
        database_conn: DatabaseConnection,
        task_map_file: Optional[str] = None,
        corrections: Optional[HDF5CorrectionSpec] = None,
) -> None:
    """
    Split a single XDF file into device-specific HDF5 files.
    Intended to be called either via the command line (via parse_arguments()) or by another script (e.g., one that
    finds and iterates over all files to be split).

    :param xdf_path: The path to the XDF file to split.
    :param database_conn: A connection interface to the Neurobooth database.
    :param task_map_file: (Optional) A YAML file containing a preset mapping of task ID -> device IDs.
    :param corrections: (Optional) Apply device-specific in-memory corrections before writing data to HDF5 files.
    """
    xdf_info = XDFInfo.parse_xdf_name(xdf_path)

    # Look up device IDs for the given task and session
    if task_map_file is not None:
        device_ids = device_id_from_yaml(task_map_file, xdf_info.task_id)
    else:
        device_ids = database_conn.get_device_ids(xdf_info)
        print(f"Got from the databse here {device_ids}")

    if not device_ids:  # Check that we found at least one device ID
        raise SplitException('Could not locate task ID {} for session {}_{}.'.format(
            xdf_info.task_id, xdf_info.subject_id, xdf_info.date.isoformat()
        ))

    # Parse the XDF, apply corrections, write the resulting HDF5, and add an entry to log_split in the database.
    try:
        device_data = xdf.parse_xdf(xdf_path, device_ids)
    except Exception as e:
        print(f"[ERROR] Error parsing XDF file {xdf_path}: {e}. Skipping file.")
        # Return the xdf_info along with an empty list so the pipeline can move on.
        return xdf_info, []
    # device_data = xdf.parse_xdf(xdf_path, device_ids)
    if corrections is not None:
        device_data = [corrections.correct_device(dev) for dev in device_data]
    # xdf.write_device_hdf5(device_data)
    device_data=rewrite_device_hdf5(xdf_path, device_data)
    # database_conn.log_split(xdf_info, device_data)
    #trying to return the data and not logging on the databse - first cut out the smaller part of data
    slim_data = []
    for dev in device_data:
        timestamps = dev.device_data.get("time_stamps", [])
        slim_data.append({
            "device_id": dev.device_id,
            "sensor_ids": dev.sensor_ids,
            "hdf5_path": dev.hdf5_path,
            "timestamps": timestamps,
            "video_files": dev.video_files,
        })

    return xdf_info, slim_data
    # return xdf_info, device_data


def parse_arguments() -> Dict[str, Any]:
    """
    Parse command line arguments.
    :return: Dictionary of keyword arguments to split().
    """
    parser = argparse.ArgumentParser(description='Split an XDF file into device-specific HDF5 files.')
    parser.add_argument(
        '--xdf',
        required=True,
        type=str,
        help="Path to the XDF file to split."
    )
    parser.add_argument(
        '--config-path',
        default=None,
        type=str,
        help="Specify a path to a Neurobooth configuration file with a 'database' entry."
    )
    parser.add_argument(
        '--ssh-tunnel',
        action='store_true',
        help=(
            "Specify this flag to SSH tunnel before connecting to the database. "
            "This is flag is not needed if running on the same machine as the database."
        )
    )
    parser.add_argument(
        '--task-device-map',
        type=str,
        default=None,
        help="If provided, the specified YAML file will be used to define a preset map of task ID -> device IDs."
    )
    parser.add_argument(
        '--hdf5-corrections',
        type=str,
        default=None,
        help="If provided, the specified YAML file will be used to locate correction functions for each device ID."
    )

    def abspath(path: Optional[str]) -> Optional[str]:
        return os.path.abspath(path) if path is not None else path

    args = parser.parse_args()
    task_map_file = abspath(args.task_device_map)
    database_conn = DatabaseConnection(abspath(args.config_path), args.ssh_tunnel)
    corrections = abspath(args.hdf5_corrections)
    if corrections is not None:
        corrections = HDF5CorrectionSpec.load(corrections)

    return {
        'xdf_path': os.path.abspath(args.xdf),
        'database_conn': database_conn,
        'task_map_file': task_map_file,
        'corrections': corrections,
    }


def main() -> None:
    """Entry point for command-line calls."""
    split(**parse_arguments())


if __name__ == '__main__':
    main()
