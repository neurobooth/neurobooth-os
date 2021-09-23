import psycopg2
from sshtunnel import SSHTunnelForwarder

from neurobooth_terra import Table, list_tables, create_table

# store stuff per table
table_dfs = dict()
column_names = dict()
dtypes = dict()

ssh_username = 'mj513'

def create_mock_database(db_name):
    """Create mock database using SSH Tunnel.

    Note: You must be on Partners VPN
    for this to work.
    """

    with SSHTunnelForwarder(
        'neurodoor.nmr.mgh.harvard.edu',
        ssh_username=ssh_username,
        ssh_config_file='~/.ssh/config',
        ssh_pkey='~/.ssh/id_rsa',
        remote_bind_address=('192.168.100.1', 5432),
        local_bind_address=('localhost', 6543)) as tunnel:

        with psycopg2.connect(database='mock_neurobooth', user='neuroboother',
                              password='neuroboothrocks', host=tunnel.local_bind_host,
                              port=tunnel.local_bind_port) as conn_mock:
            table_ids = list_tables(conn_mock)
            for table_id in table_ids:
                table = Table(table_id, conn_mock)
                print(table)

def test_neurobooth():
    """Call function to test neurobooth."""
    create_mock_database()
