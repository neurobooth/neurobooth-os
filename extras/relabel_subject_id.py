"""
This script can be used to relabel an incorrectly chosen subject ID in the database and on the file system.
REDCap-derived database tables are not affected by this script.
"""

import os
import re
import argparse
import datetime
from typing import NamedTuple, Optional, List
from itertools import chain
from psycopg2.extensions import connection

import neurobooth_os.config as nb_config


class Arguments(NamedTuple):
    """Defines the affected session and the correct ID"""
    old_id: str
    new_id: str
    date: datetime.date

    @property
    def old_session(self) -> str:
        return f'{self.old_id}_{self.date.isoformat()}'

    @property
    def new_session(self) -> str:
        return f'{self.new_id}_{self.date.isoformat()}'


class RelabelException(Exception):
    """A generic exception that occurs when attempting to relabel subject IDs."""
    pass


def main() -> None:
    args = parse_arguments()

    nb_config.load_config()
    configs = nb_config.neurobooth_config_pydantic

    relabel_database(args, database_info=configs.database)
    relabel_filesystem(args, data_dir=configs.remote_data_dir)


def parse_arguments() -> Arguments:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--id',
        type=int,
        required=True,
        help='The (incorrect/existing) subject ID of the affected session.',
    )
    parser.add_argument(
        '--date',
        type=datetime.date.fromisoformat,
        required=True,
        help='ISO-formatted (YYYY-MM-DD) date of the affected session.'
    )
    parser.add_argument(
        '--new-id',
        type=int,
        required=True,
        help='The correct subject ID.'
    )

    args = parser.parse_args()
    return Arguments(
        old_id=str(args.id),
        new_id=str(args.new_id),
        date=args.date,
    )


DATA_FILE_PATTERN = re.compile(r'.*(\d+)_([\d-]*)_.*')


def fix_filename(args: Arguments, filename: str) -> Optional[str]:
    """
    Check to see if a file corresponds to the affected session, and, if so, return the corrected file name.

    :param args: Structure describing the affected session and correct subject ID.
    :param filename: The file name to check.
    :return: None if the file name does not adhere to the expected pattern or is from a different session.
        The corrected file name otherwise.
    """
    # Check that the filename matches the expected pattern of a date file
    match = re.match(DATA_FILE_PATTERN, filename)
    if match is None:
        return None

    # Check that the file corresponds to the affected session
    subj_id = match.group(1)
    date = datetime.date.fromisoformat(match.group(2))
    if (subj_id != args.old_id) or (date != args.date):
        return None

    return filename.replace(args.old_session, args.new_session)


def relabel_filesystem(args: Arguments, data_dir: str) -> None:
    """
    Iterate through the given data directory, identify the impacted session, and update both the session directory
    and contained files. Note that this function can be imported and called from outside neurobooth OS (e.g., if data
    makes its way into long-term storage).

    :param args: Structure describing the affected session and correct subject ID.
    :param data_dir: The directory to iterate over. Should contain session-level directories.
    """
    for session_dir in os.listdir(data_dir):
        session_path = os.path.join(data_dir, session_dir)
        if not os.path.isdir(session_path) or (session_dir != args.old_session):
            continue

        for file in os.listdir(session_path):
            new_file = fix_filename(args, file)
            if new_file is None:
                continue

            old_path = os.path.join(session_path, file)
            new_path = os.path.join(session_path, new_file)
            os.rename(old_path, new_path)  # Rename file

        os.rename(session_path, os.path.join(data_dir, args.new_session))  # Rename session directory


def relabel_database(args: Arguments, database_info: nb_config.DatabaseSpec) -> None:
    """
    Correct subject IDs and file names in the database log_ tables.
    We do not currently handle the log_file table. (Could purge log_file rows and data from drwho/neo, relabel on NAS,
    and then do normal data flow.)
    :param args: Structure describing the affected session and correct subject ID.
    :param database_info: Database connection details from neurobooth OS config.
    """
    from neurobooth_os.iout import metadator
    conn: connection = metadator.get_conn(database_info.dbname)

    check_subject_table(args.new_id, conn)
    log_session_ids = relabel_log_session(args, conn)
    log_task_ids = relabel_log_task(log_session_ids, args, conn)
    relabel_log_sensor_file(log_task_ids, args, conn)
    relabel_log_application(args, conn)


def check_subject_table(subject_id: str, conn: connection) -> None:
    """
    Check whether the specified subject is present in the subject table. Raise an error if not.
    :param subject_id: The subject ID to check.
    :param conn: The database connection object.
    """
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM subject WHERE subject_id = %s", (subject_id,))
        if cursor.fetchone()[0] == 0:
            raise RelabelException(
                f'ID {subject_id} cannot be found in the database. Make sure the new subject has been added in REDCap.'
            )


def relabel_log_session(args: Arguments, conn: connection) -> List[int]:
    """
    Relabel the subject ID in the log_session table.
    :param args: Structure describing the affected session and correct subject ID.
    :param conn: The database connection object.
    :return: A list of updated log_session_id.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE log_session SET subject_id = %s
            WHERE subject_id = %s AND date = %s
            RETURNING log_session_id
            """,
            (args.new_id, args.old_id, args.date),
        )
        affected_ids = cursor.fetchall()
    return list(chain(*affected_ids))  # Flatten singleton tuples in result


def relabel_log_task(log_session_ids: List[int], args: Arguments, conn: connection) -> List[str]:
    """
    Relabel the subject ID and file names in the log_task table.
    :param log_session_ids: All tasks corresponding the provided session IDs will be relabeled.
    :param args: Structure describing the affected session and correct subject ID.
    :param conn: The database connection object.
    :return: A list of updated log_task_id.
    """
    # Identify which tasks are affected by the provided session IDs
    log_task_ids, task_notes_files, task_output_files = [], [], []
    for log_session_id in log_session_ids:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT log_task_id, task_notes_file, task_output_files
                FROM log_task WHERE log_session_id = %s
                """,
                (log_session_id,)
            )
            for log_task_id, task_notes_file, task_output_file in cursor.fetchall():
                log_task_ids.append(log_task_id)
                task_notes_files.append(task_notes_file)
                task_output_files.append(task_output_file)

    # Correct file names; there can be multiple task output files per row
    task_notes_files = [fix_filename(args, f) for f in task_notes_files]
    task_output_files = [[fix_filename(args, f) for f in files] for files in task_output_files]

    # Update impacted rows. We could speed this up, but there isn't a pressing need.
    with conn.cursor() as cursor:
        for log_task_id, task_notes_file, task_output_file in zip(log_task_ids, task_notes_files, task_output_files):
            cursor.execute(
                """
                UPDATE log_task SET
                    subject_id = %s,
                    task_notes_file = %s,
                    task_output_files = %s
                WHERE log_task_id = %s
                """,
                (args.new_id, task_notes_file, task_output_file, log_task_id)
            )

    return log_task_ids


def relabel_log_sensor_file(log_task_ids: List[str], args: Arguments, conn: connection) -> List[str]:
    # Identify which rows are affected by the provided task IDs
    log_sensor_file_ids, sensor_file_paths = [], []
    for log_task_id in log_task_ids:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT log_sensor_file_id, sensor_file_path
                FROM log_sensor_file WHERE log_task_id = %s
                """,
                (log_task_id,)
            )
            for log_sensor_file_id, sensor_file_path in cursor.fetchall():
                log_sensor_file_ids.append(log_sensor_file_id)
                sensor_file_paths.append(sensor_file_path)

    # Correct file names; there can be multiple sensor files per row
    sensor_file_paths = [[fix_filename(args, f) for f in files] for files in sensor_file_paths]

    # Update impacted rows. We could speed this up, but there isn't a pressing need.
    with conn.cursor() as cursor:
        for log_sensor_file_id, sensor_file_path in zip(log_sensor_file_ids, sensor_file_paths):
            cursor.execute(
                "UPDATE log_task SET sensor_file_path = %s WHERE log_sensor_file_id = %s",
                (sensor_file_path, log_sensor_file_id)
            )

    return log_sensor_file_ids


def relabel_log_application(args: Arguments, conn: connection) -> None:
    # Note: We will not try to alter any log messages, just associate them with the corrected ID/session
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE log_application SET
                subject_id = %s,
                session_id = %s
            WHERE subject_id = %s AND session_id = %s
            """,
            (args.new_id, args.new_session, args.old_id, args.old_session),
        )


if __name__ == '__main__':
    main()
