"""
This file splits an XDF file into constituent HDF5 files. It is meant to be called on the cluster without a full
installation of Neurobooth-OS.
"""

import os
import re
import argparse
import datetime
from typing import NamedTuple, List, Dict, Optional, Any

import psycopg2 as pg
import neurobooth_os.config as cfg
import neurobooth_os.iout.split_xdf as xdf

# TODO: pick device ID source based on date.


class SplitException(Exception):
    """For generic errors that occur when splitting an XDF file."""
    pass


XDF_NAME_PATTERN = re.compile(r'(\d+)_(\d\d\d\d-\d\d-\d\d)_\d\dh-\d\dm-\d\ds_(.*)_R001\.xdf', flags=re.IGNORECASE)


class XDFInfo(NamedTuple):
    """Structured representation of an XDF file name."""
    parent_dir: str
    name: str
    subject_id: str
    date: datetime.date
    task_id: str

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
        )


class DatabaseConnection:
    """Handles limited interactions with the Neurobooth database"""

    def __init__(self, config_path: str, tunnel: bool):
        """
        Create a new DatabaseConnection based on the provided Neurobooth-OS configuration file.
        :param config_path: The path to the Neurobooth-OS configuration, including a 'database' entry.
        :param tunnel: Whether to SSH tunnel prior to connecting. Should be False if running on neurodoor.
        """
        self.connection = DatabaseConnection.connect(config_path, tunnel)

    @staticmethod
    def connect(config_path: str, tunnel: bool) -> pg.extensions.connection:
        """
        Load and parse a Neurobooth-OS configuration, then create a psycopg2 connection.
        Note: This function copies some code from metadator.py, but importing that file introduces extra dependencies.

        :param config_path: The path to the Neurobooth-OS configuration, including a 'database' entry.
        :param tunnel: Whether to SSH tunnel prior to connecting. Should be False if running on neurodoor.
        """
        cfg.load_config(config_path, validate_paths=False)
        database_info = cfg.neurobooth_config.database

        if tunnel:
            from sshtunnel import SSHTunnelForwarder
            tunnel = SSHTunnelForwarder(
                database_info.remote_host,
                ssh_username=database_info.remote_user,
                ssh_config_file="~/.ssh/config",
                ssh_pkey="~/.ssh/id_rsa",
                remote_bind_address=(database_info.host, database_info.port),
                local_bind_address=("localhost", 6543),
            )
            tunnel.start()
            host = tunnel.local_bind_host
            port = tunnel.local_bind_port
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

    def log_split(self, xdf_info: XDFInfo, device_data: List[xdf.DeviceData]) -> None:
        with self.connection.cursor() as cursor:
            for device in device_data:
                # The file path should be session/file.hdf5 to permit comparison to log_sensor_file
                hdf5_folder, hdf5_file = os.path.split(device.hdf5_path)
                _, session_folder = os.path.split(hdf5_folder)
                hdf5_file = f'{session_folder}/{hdf5_file}'

                for sensor_id in device.sensor_ids:
                    query_params = {
                        'subject_id': xdf_info.subject_id,
                        'date': xdf_info.date.isoformat(),
                        'task_id': xdf_info.task_id,
                        'device_id': device.device_id,
                        'sensor_id': sensor_id,
                        'hdf5_file_path': hdf5_file,
                    }
                    cursor.execute(
                        """
                        INSERT INTO log_split (subject_id, date, task_id, device_id, sensor_id, hdf5_file_path)
                        VALUES (%(subject_id)s, %(date)s, %(task_id)s, %(device_id)s, %(sensor_id)s, %(hdf5_file_path)s)
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
        import yaml
        with open(file, 'r') as stream:
            task_device_map = yaml.safe_load(stream)
        return task_device_map[task_id]
    except Exception as e:
        raise SplitException(f'Could not locate task {task_id} using map file {file}.') from e


def split(
        xdf_path: str,
        database_conn: DatabaseConnection,
        task_map_file: Optional[str] = None,
) -> None:
    """
    Split a single XDF file into device-specific HDF5 files.
    Intended to be called either via the command line (via parse_arguments()) or by another script (e.g., one that
    finds and iterates over all files to be split).

    :param xdf_path: The path to the XDF file to split.
    :param database_conn: A connection interface to the Neurobooth database.
    :param task_map_file: (Optional) A YAML file containing a preset mapping of task ID -> device IDs.
    """
    xdf_info = XDFInfo.parse_xdf_name(xdf_path)

    # Look up device IDs for the given task and session
    if task_map_file is not None:
        device_ids = device_id_from_yaml(task_map_file, xdf_info.task_id)
    else:
        device_ids = database_conn.get_device_ids(xdf_info)

    if not device_ids:  # Check that we found at least one device ID
        raise SplitException('Could not locate task ID {} for session {}_{}.'.format(
            xdf_info.task_id, xdf_info.subject_id, xdf_info.date.isoformat()
        ))

    # Parse the XDF, apply corrections, write the resulting HDF5, and add an entry to log_split in the database.
    device_data = xdf.parse_xdf(xdf_path, device_ids)
    # TODO: Apply XDF corrections
    xdf.write_device_hdf5(device_data)
    database_conn.log_split(xdf_info, device_data)


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

    args = parser.parse_args()
    task_map_file = os.path.abspath(args.task_device_map) if (args.task_device_map is not None) else None
    database_conn = DatabaseConnection(os.path.abspath(args.config_path), args.ssh_tunnel)
    return {
        'xdf_path': os.path.abspath(args.xdf),
        'database_conn': database_conn,
        'task_map_file': task_map_file,
    }


def main() -> None:
    """Entry point for command-line calls."""
    split(**parse_arguments())


if __name__ == '__main__':
    main()
