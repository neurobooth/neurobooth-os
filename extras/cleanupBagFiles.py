"""
Script to fix database records in the log_sensor_file table.

The log_sensor_file table contains a TEXT[] column called 'sensor_file_path'. For intel cameras, this column
should contain two elements, one for an hdf5 file path, and one for the path of the corresponding bag file.
In some cases, the bag file path element is missing.

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

# with_bag_query = """SELECT DISTINCT log_sensor_file_test.*
#     FROM log_sensor_file_test
#
#     WHERE UPPER(device_id) LIKE 'INTEL%'
#
#     AND EXISTS (
#         -- At least one element must match the first pattern
#         SELECT 1 FROM unnest(sensor_file_path) AS elem
#         WHERE elem LIKE '%hdf5'
#     )
#     AND EXISTS (
#         -- No element should match the exclusion pattern
#         SELECT 1 FROM unnest(sensor_file_path) AS elem
#         WHERE elem LIKE '%bag'
#     );
#     """

without_bag_query = """SELECT DISTINCT  log_sensor_file_test.* 
    FROM  log_sensor_file_test

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


def _get_bag_file_name(device, hdf5_text) -> str:
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
    else:
        pass
    if first_part:
        result = first_part + "intel" + intel_number + ".bag"
    return result


def add_bag_element(conn: connection, pkey: str, bag_element: str):
    update_sql = """
        UPDATE  log_sensor_file_test 
        SET sensor_file_path = array_append(sensor_file_path, %(bag_element)s)
        WHERE log_sensor_file_id = %(pkey)s;
        """
    with conn.cursor() as cursor:
        cursor.execute(update_sql, {'pkey': pkey, 'bag_element': bag_element})


def run():
    nb_config.load_config(validate_paths=False)

    db = nb_config.neurobooth_config.database
    update_count = 0

    with meta.get_database_connection() as conn:
        query_results = _get_records(conn, without_bag_query)
        for row in query_results:
            string_list = row[8]  # 9th element (0-based indexing)
            device = row[6]
            id = row[0]
            for string_item in string_list:
                print(string_item)
                if 'hdf5' in string_item:
                    bag_element = _get_bag_file_name(device, string_item)
                    add_bag_element(conn, id, bag_element)
                    print(f"Added bag: {bag_element}")
                    update_count += 1
                    print(update_count)
            print("")
    print(f"Updates: {update_count}")

    print(len(query_results))


# def run_test():
#     nb_config.load_config(validate_paths=False)
#
#     db = nb_config.neurobooth_config.database
#
#     with meta.get_database_connection() as conn:
#         query_results = _get_records_with_bag_file(conn)
#         failure_count = 0
#         success_count = 0
#         for row in query_results:
#             string_list = row[8]  # 9th element (0-based indexing)
#             device = row[6]
#             bag_file_name = None
#             hdf_name = None
#             for string_item in string_list:
#                 # print(device)
#                 if 'hdf5' in string_item:
#                     hdf_name = string_item
#                     bag_file_name = _get_bag_file_name(device, string_item)
#
#                 elif 'bag' in string_item:
#                     if bag_file_name == string_item:
#                         # print ("SUCCESS!!")
#                         success_count += 1
#                     else:
#                         # print(f"Processing hdf5: {string_item}")
#                         print(f'{hdf_name} hdf')
#                         print(f'{string_item} actual')
#                         print(f'{bag_file_name} constructed')
#                         print("************************* FAILURE **************************************************")
#                         failure_count += 1
#         print(f'failures {failure_count}')
#         print(f'successes {success_count}')


# def _get_records_with_bag_file(conn: connection) -> Tuple:
#     """
#     Retrieve records where there is both an hdf5 file and a bag file element in the text array column SENSOR_FILE_PATH.
#
#     :param conn: The database connection object.
#     """
#     return _get_records(conn, with_bag_query)


# def _get_records_without_bag_file(conn: connection) -> Tuple:
#     return _get_records(conn, without_bag_query)


def _get_records(conn: connection, query: str) -> List[Tuple]:
    try:
        with conn.cursor() as cursor:
            cursor.execute(query)
            results = cursor.fetchall()

            if not results:
                raise conn.DatabaseError(
                    'An error occurred executing query. No results found.'
                )

            return results

    except psycopg2.Error as e:
        print(f"Database error: {e}")
        raise e


if __name__ == '__main__':
    run()