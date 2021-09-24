import psycopg2
from sshtunnel import SSHTunnelForwarder

from neurobooth_terra import Table, list_tables, create_table

# store stuff per table
table_dfs = dict()
column_names = dict()
dtypes = dict()

ssh_username = 'mj513'


def insert_mock_rows(conn_mock):
    """Create mock database using SSH Tunnel.

    Parameters
    ----------
    conn_mock : instance of psychopg2.connection
        The connection object to the mock database

    Notes
    -----
    You must be on Partners VPN for this to work.
    """
    table_ids = list_tables(conn_mock)

    table = Table('study', conn_mock)
    table.insert_rows([('mock_study', 0, 'mock_study', 0, 0,
                        '{mock_collection}', None, None)])

    table = Table('collection', conn_mock)
    table.insert_rows([('mock_collection', False, '{mock_obs}', None)])

    table = Table('stimulus', conn_mock)
    table.insert_rows([('mock_test_1', 'description', 2, None,
                        'stream_python',
                        'tasks.test.mock_test.py::mock_stim()',
                        None, None)])

    table = Table('tech_obs_data', conn_mock)
    table.insert_rows([('mock_obs', None, 'testing', None, None, None,
                        'mock_test_1', '{mock_dev_1, mock_mbient_1, mock_Intel_1}',
                        None, None, None, None,
                        '{{mock_sens_1, ""},{mock_mbient_acc_1, mock_mbient_grad_1},{mock_Intel_rgb_1, mock_Intel_depth_1}}')])

    table = Table('device', conn_mock)
    table.insert_rows([('mock_dev_1', 0, False, 0, 'mock', 'mock_make',
                        'neurobooth inc', 0, '{mock_sens_1}')])
    table.insert_rows([('mock_mbient_1', 0, False, 0, 'mock',
                        'mock_make', 'neurobooth inc', 0,
                        '{mock_mbient_acc_1, mock_mbient_grad_1}')])
    table.insert_rows([('mock_Intel_1', 0, False, 0, 'mock',
                        'mock_make', 'neurobooth inc', 0,
                        '{mock_Intel_rgb_1, mock_Intel_depth_1}')])

    table = Table('sensor', conn_mock)
    table.insert_rows([('mock_sens_1', 100, None, None, 'edf', None)])
    table.insert_rows([('mock_mbient_acc_1', 100, None, None, 'edf', None)])
    table.insert_rows([('mock_mbient_grad_1', 100, None, None, 'edf', None)])
    table.insert_rows([('mock_Intel_rgb_1', 180, 1080, 720, 'bag', None)])
    table.insert_rows([('mock_Intel_depth_1', 180, 1080, 720, 'bag', None)])


def delete_mock_rows(conn_mock):
    """Delete mock.

    Parameters
    ----------
    conn_mock : instance of psychopg2.connection
        The connection object to the mock database.
    """
    table_ids = ['study', 'collection', 'tech_obs_data', 'device',
                    'sensor', 'stimulus']
    primary_keys = ['study_id', 'collection_id', 'tech_obs_id',
                    'device_id', 'sensor_id', 'stimulus_id']
    for table_id, pk in zip(table_ids, primary_keys):
        table = Table(table_id, conn_mock)
        table.delete_row(f"{pk} LIKE 'mock%'")


def test_neurobooth():
    """Call function to test neurobooth."""
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
            delete_mock_rows(conn_mock)
            insert_mock_rows(conn_mock)
            delete_mock_rows(conn_mock)
