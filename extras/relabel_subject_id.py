"""
This script can be used to relabel an incorrectly chosen subject ID in the database and on the file system.
REDCap-derived database tables are not affected by this script.

This script currently operates at the day level, without consideration of session time.
"""

import os
import re
import sys
import logging
import argparse
import datetime
from typing import NamedTuple, Optional, List
from itertools import chain
from psycopg2.extensions import connection

import neurobooth_os.config as nb_config


LOGGER: Optional[logging.Logger] = None


class RelabelParams(NamedTuple):
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
    nb_config.load_config()
    args = parse_arguments()

    try:
        configs = nb_config.neurobooth_config_pydantic

        LOGGER.info('Applying Database Updates')
        relabel_database(args, database_info=configs.database)

        LOGGER.info('Renaming files in NAS')
        relabel_filesystem(args, data_dir=configs.remote_data_dir)
    except RelabelException as e:
        LOGGER.error(e, exc_info=sys.exc_info())
        raise e
    except Exception as e:
        LOGGER.critical(f'Uncaught exception: {e}', exc_info=sys.exc_info())
        raise e
    finally:
        logging.shutdown()


def parse_arguments() -> RelabelParams:
    """
    Parse command line arguments and set up logging as a side effect.
    :return: Structure describing the affected session and correct subject ID.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--id',
        type=str,
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
        type=str,
        required=True,
        help='The correct subject ID.'
    )
    parser.add_argument(
        '--no-log',
        action='store_true',
        help='Disable database logging.'
    )

    args = parser.parse_args()
    setup_logging(not args.no_log)
    return RelabelParams(
        old_id=args.id,
        new_id=args.new_id,
        date=args.date,
    )


def setup_logging(enabled: bool) -> None:
    """
    Set up database logging if enabled. If disabled, just sent messages to the console.
    :param enabled: Whether database logging is enabled.
    """
    global LOGGER
    if enabled:
        from neurobooth_os.log_manager import make_db_logger
        LOGGER = make_db_logger()
    else:
        LOGGER = logging.getLogger('Console')
        LOGGER.addHandler(logging.StreamHandler(sys.stdout))


DATA_FILE_PATTERN = re.compile(r'.*?(\d+)_(\d+-\d+-\d+)[_-].*')


def fix_filename(args: RelabelParams, filename: str) -> Optional[str]:
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


def relabel_filesystem(args: RelabelParams, data_dir: str) -> None:
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

            # Rename file
            old_path = os.path.join(session_path, file)
            new_path = os.path.join(session_path, new_file)
            LOGGER.info(f'RENAME FILE {old_path} -> {new_path}')
            os.rename(old_path, new_path)

        # Rename session directory
        new_session_path = os.path.join(data_dir, args.new_session)
        LOGGER.info(f'RENAME DIRECTORY {session_path} -> {new_session_path}')
        os.rename(session_path, new_session_path)


def relabel_database(args: RelabelParams, database_info: nb_config.DatabaseSpec) -> None:
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

    LOGGER.info('COMMIT DATABASE CHANGES')
    conn.commit()
    conn.close()


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


def relabel_log_session(args: RelabelParams, conn: connection) -> List[int]:
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
    affected_ids = list(chain(*affected_ids))  # Flatten singleton tuples in result
    LOGGER.info(f'UPDATE log_session: {affected_ids}')
    return affected_ids


def relabel_log_task(log_session_ids: List[int], args: RelabelParams, conn: connection) -> List[str]:
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
    task_output_files = [
        [fix_filename(args, f) for f in files] if files else files
        for files in task_output_files
    ]

    # Update impacted rows. We could speed this up, but there isn't a pressing need.
    with conn.cursor() as cursor:
        for log_task_id, task_notes_file, task_output_file in zip(log_task_ids, task_notes_files, task_output_files):
            if task_notes_file is None or None in task_output_file:
                raise RelabelException(f'Error renaming files for log_task_id={log_task_id}.')

            LOGGER.info(f'UPDATE log_task {log_task_id}: {task_notes_file}, {task_output_file}')
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


def relabel_log_sensor_file(log_task_ids: List[str], args: RelabelParams, conn: connection) -> List[str]:
    """
    Relabel the file names in the log_sensor_file table.

    :param log_task_ids: All rows corresponding the provided task IDs will be relabeled.
    :param args: Structure describing the affected session and correct subject ID.
    :param conn: The database connection object.
    :return: A list of updated log_sensor_file_id.
    """
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
    sensor_file_paths = [
        [fix_filename(args, f) for f in files] if files else files
        for files in sensor_file_paths
    ]

    # Update impacted rows. We could speed this up, but there isn't a pressing need.
    with conn.cursor() as cursor:
        for log_sensor_file_id, sensor_file_path in zip(log_sensor_file_ids, sensor_file_paths):
            if None in sensor_file_path:
                raise RelabelException(f'Error renaming files for log_sensor_file_id={log_sensor_file_id}.')

            LOGGER.info(f'UPDATE log_sensor_file {log_sensor_file_id}: {sensor_file_path}')
            cursor.execute(
                "UPDATE log_sensor_file SET sensor_file_path = %s WHERE log_sensor_file_id = %s",
                (sensor_file_path, log_sensor_file_id)
            )

    return log_sensor_file_ids


def relabel_log_application(args: RelabelParams, conn: connection) -> List[int]:
    """
    Relabel the subject ID and session ID in the log_application table.
    Note: We do not try to alter any log messages, just associate them with the corrected ID/session

    :param args: Structure describing the affected session and correct subject ID.
    :param conn: The database connection object.
    :return: A list of updated row ids.
    """
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE log_application SET
                subject_id = %s,
                session_id = %s
            WHERE subject_id = %s AND session_id = %s
            RETURNING id
            """,
            (args.new_id, args.new_session, args.old_id, args.old_session),
        )
        affected_ids = cursor.fetchall()

    affected_ids = list(chain(*affected_ids))  # Flatten singleton tuples in result
    LOGGER.info(f'UPDATE log_application: {affected_ids}')
    return affected_ids


if __name__ == '__main__':
    main()
