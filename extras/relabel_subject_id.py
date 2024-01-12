"""
This script can be used to relabel an incorrectly chosen subject ID in the database and on the file system.
REDCap-derived database tables are not affected by this script.
"""

import os
import re
import argparse
import datetime
from typing import TYPE_CHECKING, NamedTuple, Optional

import neurobooth_os.config as nb_config

if TYPE_CHECKING:
    from psycopg2.extensions import connection


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
            new_file = fix_filename(file)
            if new_file is None:
                continue

            old_path = os.path.join(session_path, file)
            new_path = os.path.join(session_path, new_file)
            os.rename(old_path, new_path)  # Rename file

        os.rename(session_path, os.path.join(data_dir, args.new_session))  # Rename session directory


def relabel_database(args: Arguments, database_info: nb_config.DatabaseSpec) -> None:
    from neurobooth_os.iout import metadator
    conn: connection = metadator.get_conn(database_info.dbname)

    check_subject_table(args.new_id, conn)
    relabel_log_session(args, conn)
    relabel_log_task(args, conn)
    # TODO: log_file?
    # TODO: log_sensor_file

    relabel_log_application(args, conn)


def check_subject_table(subject_id: str, conn: connection) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM subject WHERE subject_id = %s", subject_id)
        if cursor.fetchone() == 0:
            raise RelabelException(
                f'ID {subject_id} cannot be found in the database. Make sure the new subject has been added in REDCap.'
            )


def relabel_log_session(args: Arguments, conn: connection) -> None:
    # TODO: Look into returning log_session_id to support other updates
    with conn.cursor() as cursor:
        cursor.execute(
            "UPDATE log_session SET subject_id = %s WHERE subject_id = %s AND date = %s",
            (args.new_id, args.old_id, args.date),
        )


def relabel_log_task(args: Arguments, conn: connection) -> None:
    # TODO: Look into returning log_task_id to support other updates
    # TODO: Need to handle subject_id, task_notes_file and task_output_files
    pass


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
