import uuid
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

        with psycopg2.connect(database='neurobooth', user='neuroboother',
                              password='neuroboothrocks', host=tunnel.local_bind_host,
                              port=tunnel.local_bind_port) as conn:

            # neurobooth database is set with is_template = True
            # and neuroboother has privileges of CREATE_DB and REPLICATION
            # for this to work. autocommit=True since CREATE DATABASE
            # cannot work in transaction block.
            conn.set_session(autocommit=True)
            cursor = conn.cursor()
            cmd = f'CREATE DATABASE {db_name} WITH TEMPLATE neurobooth'
            cursor.execute(cmd)
            cursor.close()
            conn.set_session(autocommit=False)

            table_ids = list_tables(conn)
            for table_id in table_ids:
                print(f'Table: {table_id}')
                table = Table(table_id, conn)
                table_dfs[table_id] = table.query(f'SELECT * from {table_id}')
                column_names[table_id] = table.column_names
                dtypes[table_id] = table.data_types

        with psycopg2.connect(database=db_name, user='neuroboother',
                              password='neuroboothrocks', host=tunnel.local_bind_host,
                              port=tunnel.local_bind_port) as conn_mock:
            for table_id in table_ids:
                table = Table(table_id, conn_mock)
                print(table)

def delete_mock_database(db_name):

    with SSHTunnelForwarder(
        'neurodoor.nmr.mgh.harvard.edu',
        ssh_username=ssh_username,
        ssh_config_file='~/.ssh/config',
        ssh_pkey='~/.ssh/id_rsa',
        remote_bind_address=('192.168.100.1', 5432),
        local_bind_address=('localhost', 6543)) as tunnel:

        with psycopg2.connect(database='neurobooth', user='neuroboother',
                              password='neuroboothrocks', host=tunnel.local_bind_host,
                              port=tunnel.local_bind_port) as conn:
            conn.set_session(autocommit=True)
            cursor = conn.cursor()
            cmd = f'DROP DATABASE {db_name}'
            cursor.execute(cmd)
            cursor.close()
            conn.set_session(autocommit=False)


def test_neurobooth():
    """Call function to test neurobooth."""
    db_name = 'TEST_' + uuid.uuid4().hex.upper()[0:6]  # random name
    
    try:
        create_mock_database(db_name)

    # add test functions here
    except Exception as e:
        delete_mock_database(db_name)
        raise(e)

