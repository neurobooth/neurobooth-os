"""Shared database connection helper for perf scripts.

Reads credentials from db_credentials.json (git-ignored).

If ``ssh_host`` is set, the connection goes through an SSH tunnel. If it is
omitted or empty (e.g. a single-laptop booth with a local database), the
script connects directly to ``db_host``/``db_port``.
"""

import json
from pathlib import Path
from typing import Tuple, Union

import psycopg2
from sshtunnel import SSHTunnelForwarder

_CREDS_FILE = Path(__file__).parent / "db_credentials.json"


class _NoTunnel:
    """Stand-in for SSHTunnelForwarder on direct connections, so callers can
    call ``tunnel.stop()`` unconditionally."""

    def stop(self) -> None:
        pass


def _load_credentials() -> dict:
    """Load database credentials from the JSON file."""
    if not _CREDS_FILE.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {_CREDS_FILE}\n"
            "Copy db_credentials.example.json (SSH tunnel) or "
            "db_credentials.local.example.json (local DB) to "
            "db_credentials.json and fill in your credentials."
        )
    with open(_CREDS_FILE) as f:
        return json.load(f)


def get_conn() -> Tuple[
    psycopg2.extensions.connection, Union[SSHTunnelForwarder, _NoTunnel]
]:
    """Connect to the database, via SSH tunnel if ``ssh_host`` is configured.

    Returns:
        A ``(conn, tunnel)`` tuple. ``tunnel.stop()`` is always safe to call.
    """
    creds = _load_credentials()
    if creds.get("ssh_host"):
        tunnel = SSHTunnelForwarder(
            creds["ssh_host"],
            ssh_username=creds["ssh_username"],
            ssh_pkey=str(Path.home() / ".ssh" / creds["ssh_pkey_filename"]),
            remote_bind_address=(creds["remote_db_host"], creds["remote_db_port"]),
            local_bind_address=("localhost", creds.get("local_bind_port", 0)),
        )
        tunnel.start()
        host, port = "localhost", tunnel.local_bind_port
    else:
        tunnel = _NoTunnel()
        host = creds.get("db_host", "localhost")
        port = creds.get("db_port", 5432)
    conn = psycopg2.connect(
        database=creds["db_name"],
        user=creds["db_user"],
        password=creds["db_password"],
        host=host,
        port=port,
    )
    return conn, tunnel
