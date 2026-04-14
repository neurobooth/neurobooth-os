"""Shared database connection helper for perf scripts.

Reads credentials from db_credentials.json (git-ignored).
"""

import json
from pathlib import Path
from typing import Tuple

import psycopg2
from sshtunnel import SSHTunnelForwarder

_CREDS_FILE = Path(__file__).parent / "db_credentials.json"


def _load_credentials() -> dict:
    """Load database credentials from the JSON file."""
    if not _CREDS_FILE.exists():
        raise FileNotFoundError(
            f"Credentials file not found: {_CREDS_FILE}\n"
            "Copy db_credentials.example.json to db_credentials.json "
            "and fill in your credentials."
        )
    with open(_CREDS_FILE) as f:
        return json.load(f)


def get_conn() -> Tuple[psycopg2.extensions.connection, SSHTunnelForwarder]:
    """Connect to the database via SSH tunnel. Returns (conn, tunnel)."""
    creds = _load_credentials()
    tunnel = SSHTunnelForwarder(
        creds["ssh_host"],
        ssh_username=creds["ssh_username"],
        ssh_pkey=str(Path.home() / ".ssh" / creds["ssh_pkey_filename"]),
        remote_bind_address=(creds["remote_db_host"], creds["remote_db_port"]),
        local_bind_address=("localhost", creds.get("local_bind_port", 0)),
    )
    tunnel.start()
    conn = psycopg2.connect(
        database=creds["db_name"],
        user=creds["db_user"],
        password=creds["db_password"],
        host="localhost",
        port=tunnel.local_bind_port,
    )
    return conn, tunnel
