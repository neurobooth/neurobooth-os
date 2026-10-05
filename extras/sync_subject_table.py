"""Sync the ``subject`` table from a source database into this booth's database.

The source database (e.g. the Merrimac ``FA_study`` database on neurodoor2) is the
source of truth and is opened read-only. The target is the database named in this
booth's neurobooth config (e.g. ``dod_neurobooth``).

Rules:
    - Source rows whose ``subject_id`` is missing from the target are inserted.
    - Target rows whose ``subject_id`` exists in the source are overwritten with the
      source values when they differ.
    - Target rows whose ``subject_id`` is absent from the source are left alone.
    - Rows are never deleted.

The source credentials file is a JSON file with the keys ``ssh_host``,
``ssh_username``, ``ssh_pkey_filename`` (in ``~/.ssh``), ``remote_db_host``,
``remote_db_port``, ``db_name``, ``db_user`` and ``db_password``. Keep it out of the
repo (``db_credentials*.json`` is git-ignored).

Usage:
    python extras\\sync_subject_table.py --source-creds PATH          # dry run
    python extras\\sync_subject_table.py --source-creds PATH --apply  # write
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import psycopg2
from neurobooth_terra import Table
from psycopg2.extensions import connection
from sshtunnel import SSHTunnelForwarder

from neurobooth_os.config import load_config_by_service_name
from neurobooth_os.iout import metadator
from neurobooth_os.iout.db_connection import ManagedConnection

LOGGER = logging.getLogger("sync_subject_table")

TABLE_NAME = "subject"
KEY_COLUMN = "subject_id"


def connect_source(creds_path: Path) -> ManagedConnection:
    """Open a read-only connection to the source database through an SSH tunnel.

    Args:
        creds_path: Path to the source database credentials JSON file.

    Returns:
        A read-only connection; closing it also stops the SSH tunnel.
    """
    with open(creds_path) as f:
        creds = json.load(f)
    tunnel = SSHTunnelForwarder(
        creds["ssh_host"],
        ssh_username=creds["ssh_username"],
        ssh_pkey=str(Path.home() / ".ssh" / creds["ssh_pkey_filename"]),
        remote_bind_address=(creds["remote_db_host"], creds["remote_db_port"]),
        local_bind_address=("localhost", 0),
    )
    tunnel.start()
    try:
        conn = psycopg2.connect(
            database=creds["db_name"],
            user=creds["db_user"],
            password=creds["db_password"],
            host="localhost",
            port=tunnel.local_bind_port,
        )
    except Exception:
        tunnel.stop()
        raise
    conn.set_session(readonly=True)
    return ManagedConnection(conn, tunnel)


def fetch_subjects(conn: connection, cols: Sequence[str]) -> Dict[str, tuple]:
    """Read every row of the subject table.

    Args:
        conn: Database connection.
        cols: Columns to select, in order; must include the key column.

    Returns:
        Rows as tuples ordered like ``cols``, keyed by subject ID.
    """
    key_index = list(cols).index(KEY_COLUMN)
    col_list = ", ".join(f'"{col}"' for col in cols)
    with conn.cursor() as cur:
        cur.execute(f"SELECT {col_list} FROM {TABLE_NAME}")
        return {row[key_index]: row for row in cur.fetchall()}


def find_rows_to_upsert(
    source: Dict[str, tuple], target: Dict[str, tuple]
) -> Tuple[List[tuple], List[tuple]]:
    """Find the source rows that the target needs inserted or updated.

    Target-only rows are never returned, so they are left untouched.

    Args:
        source: Source rows keyed by subject ID (the source of truth).
        target: Target rows keyed by subject ID.

    Returns:
        A ``(new_rows, changed_rows)`` tuple. ``new_rows`` are source rows whose
        subject ID is missing from the target; ``changed_rows`` are source rows
        whose subject ID is in the target with different values.
    """
    new_rows = []
    changed_rows = []
    for subject_id, row in sorted(source.items()):
        if subject_id not in target:
            new_rows.append(row)
        elif target[subject_id] != row:
            changed_rows.append(row)
    return new_rows, changed_rows


def sync(source_creds: Path, apply: bool) -> None:
    """Upsert source subject rows into the booth's database.

    Args:
        source_creds: Path to the source database credentials JSON file.
        apply: Write the changes; if False, only report them.

    Raises:
        RuntimeError: If the source and target subject tables have different
            columns.
    """
    load_config_by_service_name("CTR")
    target_conn = metadator.get_database_connection()
    try:
        source_conn = connect_source(source_creds)
        try:
            cols = Table(TABLE_NAME, conn=source_conn).column_names
            target_table = Table(TABLE_NAME, conn=target_conn)
            if sorted(cols) != sorted(target_table.column_names):
                raise RuntimeError(
                    f"{TABLE_NAME} columns differ: source={cols}, "
                    f"target={target_table.column_names}"
                )
            source = fetch_subjects(source_conn, cols)
        finally:
            source_conn.close()

        target = fetch_subjects(target_conn, cols)
        new_rows, changed_rows = find_rows_to_upsert(source, target)
        key_index = cols.index(KEY_COLUMN)
        LOGGER.info(
            f"source={len(source)} rows, target={len(target)} rows, "
            f"target-only (left alone)={len(target.keys() - source.keys())}"
        )
        LOGGER.info(f"new={[row[key_index] for row in new_rows]}")
        LOGGER.info(f"changed={[row[key_index] for row in changed_rows]}")

        rows = new_rows + changed_rows
        if not rows:
            LOGGER.info("Nothing to do")
        elif not apply:
            LOGGER.info(f"Dry run: {len(rows)} rows not written (use --apply)")
        else:
            target_table.insert_rows(
                rows, cols, on_conflict="update", conflict_cols=[KEY_COLUMN]
            )
            LOGGER.info(
                f"Wrote {len(new_rows)} inserts and {len(changed_rows)} updates"
            )
    finally:
        target_conn.close()


def main() -> None:
    """Parse arguments and run the sync; exit non-zero on failure."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--source-creds",
        type=Path,
        required=True,
        help="Credentials JSON for the source (read-only) database",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the changes (default: dry run, report only)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    try:
        sync(args.source_creds, args.apply)
    except Exception:
        LOGGER.exception("Subject sync failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
