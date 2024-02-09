import psycopg2
from sshtunnel import SSHTunnelForwarder

from neurobooth_os.mock import insert_mock_rows, delete_mock_rows
import neurobooth_os.config as cfg


def test_neurobooth_mock():
    """Call function to test neurobooth."""

    with SSHTunnelForwarder(
        "neurodoor.nmr.mgh.harvard.edu",
        ssh_username=cfg.neurobooth_config.database.remote_user,
        ssh_config_file="~/.ssh/config",
        ssh_pkey="~/.ssh/id_rsa",
        remote_bind_address=("192.168.100.1", 5432),
        local_bind_address=("localhost", 6543),
    ) as tunnel:

        with psycopg2.connect(
            database=cfg.neurobooth_config.database.dbname,
            user=cfg.neurobooth_config.database.user,
            password=cfg.neurobooth_config.database.password,
            host=tunnel.local_bind_host,
            port=tunnel.local_bind_port,
        ) as conn_mock:
            delete_mock_rows(conn_mock)
            insert_mock_rows(conn_mock)
            delete_mock_rows(conn_mock)
