"""Shared database connection helper for perf scripts.

Reads credentials from db_credentials.json (git-ignored). To target another
database, pass ``--creds <name>`` to a script to read db_credentials.<name>.json
instead (e.g. ``--creds merrimac`` for the Merrimac production database).
Templates: db_credentials.SITE_NAME.example.json (remote DB over an SSH tunnel)
and db_credentials.local.example.json (local DB).

If ``ssh_host`` is set, the connection goes through an SSH tunnel. If it is
omitted or empty (e.g. a single-laptop booth with a local database), the
script connects directly to ``db_host``/``db_port``.
"""

import argparse
import json
from pathlib import Path
from typing import Optional, Tuple, Union

import psycopg2
from sshtunnel import SSHTunnelForwarder

_PERF_DIR = Path(__file__).parent


class _NoTunnel:
    """Stand-in for SSHTunnelForwarder on direct connections, so callers can
    call ``tunnel.stop()`` unconditionally."""

    def stop(self) -> None:
        pass


def add_creds_argument(parser: argparse.ArgumentParser) -> None:
    """Add the ``--creds NAME`` option that selects the credentials file.

    Args:
        parser: The script's argument parser.
    """
    parser.add_argument(
        "--creds",
        default=None,
        metavar="NAME",
        help="Use extras/perf/db_credentials.NAME.json (e.g. merrimac) "
        "instead of db_credentials.json",
    )


def _creds_file(creds: Optional[str]) -> Path:
    """Return the credentials file for ``creds`` (the default file if None)."""
    if not creds:
        return _PERF_DIR / "db_credentials.json"
    return _PERF_DIR / f"db_credentials.{creds}.json"


def _load_credentials(creds: Optional[str]) -> dict:
    """Load database credentials from the JSON file."""
    creds_file = _creds_file(creds)
    if not creds_file.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {creds_file}\n"
            f"Copy a db_credentials*.example.json template from {_PERF_DIR} to "
            f"{creds_file.name} and fill in your credentials."
        )
    with open(creds_file) as f:
        return json.load(f)


def get_conn(
    creds: Optional[str] = None,
) -> Tuple[psycopg2.extensions.connection, Union[SSHTunnelForwarder, _NoTunnel]]:
    """Connect to the database, via SSH tunnel if ``ssh_host`` is configured.

    Args:
        creds: Credentials name; reads db_credentials.<creds>.json. ``None``
            reads db_credentials.json.

    Returns:
        A ``(conn, tunnel)`` tuple. ``tunnel.stop()`` is always safe to call.
    """
    creds_data = _load_credentials(creds)
    if creds_data.get("ssh_host"):
        tunnel = SSHTunnelForwarder(
            creds_data["ssh_host"],
            ssh_username=creds_data["ssh_username"],
            ssh_pkey=str(Path.home() / ".ssh" / creds_data["ssh_pkey_filename"]),
            remote_bind_address=(
                creds_data["remote_db_host"],
                creds_data["remote_db_port"],
            ),
            local_bind_address=("localhost", creds_data.get("local_bind_port", 0)),
        )
        tunnel.start()
        host, port = "localhost", tunnel.local_bind_port
    else:
        tunnel = _NoTunnel()
        host = creds_data.get("db_host", "localhost")
        port = creds_data.get("db_port", 5432)
    conn = psycopg2.connect(
        database=creds_data["db_name"],
        user=creds_data["db_user"],
        password=creds_data["db_password"],
        host=host,
        port=port,
    )
    return conn, tunnel
