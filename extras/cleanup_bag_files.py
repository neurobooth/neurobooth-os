"""
Script to fix database records in the log_sensor_file table.

The log_sensor_file table contains a TEXT[] column called 'sensor_file_path'. For intel cameras, this column
should contain two elements, one for an hdf5 file path, and one for the path of the corresponding bag file.
In some cases, the bag file path element is missing. This, in turn, prevents the bag file from being deleted after it is
moved to long-term storage.

This script finds any records in the log sensor file where the device is an Intel camera (as derived from the device_id
column) and there is an hdf5 file element but no corresponding bag file.  In these situations, a bag file path is
created from the info in the hdf5 fie path. This new path is appended to the list in the sensor_file_path column.

"""
from typing import Tuple, List

from psycopg2.extensions import connection
import psycopg2
import re

import neurobooth_os.config as nb_config
import neurobooth_os.iout.metadator as meta

without_bag_query = """SELECT DISTINCT  log_sensor_file.* 
    FROM  log_sensor_file

    WHERE UPPER(device_id) LIKE 'INTEL%'

    AND EXISTS (
        -- At least one element must match the first pattern
        SELECT 1 FROM unnest(sensor_file_path) AS elem 
        WHERE elem LIKE '%hdf5'
    )
    AND NOT EXISTS (
        -- No element should match the exclusion pattern
        SELECT 1 FROM unnest(sensor_file_path) AS elem 
        WHERE elem LIKE '%bag'
    );
    """


def _get_bag_file_name(device: str, hdf5_text: str) -> str:
    """
    Returns a bag file name and path based on the device name and the path for the hdf5 file. Because the naming
    conventions were not applied consistently, we have to handle multiple variations
    Parameters
    ----------
    device      the device id
    hdf5_text   the full path and file name of the hdf5 file

    Returns
    -------
    The newly constructed path, or None

    """
    match1 = re.match(r'.*?obs_1_', hdf5_text)  # Matches cases with _obs_1
    match2 = re.match(r'.*?R001', hdf5_text)    # Matches cases without 'obs' in the string
    match = re.match(r'.*?obs_', hdf5_text)     # Matches cases with "_obs_", but not "_obs_1"
    result = None
    first_part = None
    intel_number = device[-1]
    if match1:
        first_part = match1.group(0)
    elif match:
        first_part = match.group(0)
    elif match2:
        first_part = match2.group(0).replace("R001", "")
    # else:
    #     pass
    if first_part:
        result = first_part + "intel" + intel_number + ".bag"
    return result


def add_bag_element(conn: connection, pkey: str, bag_element: str) -> None:
    """
    Performs the database update that appends the bag file path to the sensor_file_path column

    Parameters
    ----------
    conn        database connection
    pkey        the primary key for the record to update
    bag_element the file path string to append

    Returns
    -------
    None

    """
    update_sql = """
        UPDATE  log_sensor_file 
        SET sensor_file_path = array_append(sensor_file_path, %(bag_element)s)
        WHERE log_sensor_file_id = %(pkey)s;
        """
    with conn.cursor() as cursor:
        cursor.execute(update_sql, {'pkey': pkey, 'bag_element': bag_element})


def run() -> None:
    """
    Runs the routine for adding missing bag file paths, it iterates over a list of records that have no bag file,
    constructs the bag file entry and appends it to the appropriate record

    Returns
    -------
    None
    """
    nb_config.load_config(validate_paths=False)

    db = nb_config.neurobooth_config.database

    with meta.get_database_connection() as conn:
        query_results = _get_records(conn, without_bag_query)
        for row in query_results:
            string_list = row[8]  # 9th element (0-based indexing)
            device = row[6]
            id = row[0]
            for string_item in string_list:
                if 'hdf5' in string_item:
                    bag_element = _get_bag_file_name(device, string_item)
                    add_bag_element(conn, id, bag_element)


def _get_records(conn: connection, query: str) -> List[Tuple]:
    """

    Parameters
    ----------
    conn        the database connection
    query       the query string to run

    Returns
    -------
    A list of Tuples, with each tuple representing a record from the log_sensor_file table
    """
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return cursor.fetchall()

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        raise e


if __name__ == '__main__':
    run()