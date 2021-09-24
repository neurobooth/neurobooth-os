import psycopg2
from sshtunnel import SSHTunnelForwarder

from neurobooth_terra import Table, list_tables, create_table

# store stuff per table
table_dfs = dict()
column_names = dict()
dtypes = dict()

ssh_username = 'mj513'

def create_mock_database():
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

            table = Table('study', conn_mock)
            table.insert_rows([('mock_study', 0, 'mock_study', 0, 0,
                                '{mock_collection}', None, None)])

            table = Table('collections', conn_mock)
            table.insert_rows([('mock_collection', False, '{mock_obs}', None)])

            table = Table('tech_obs_data', conn_mock)
            table.insert_rows([('mock_obs', None, 'testing', None, None, None,
                                'mock_test_1', '{mock_dev_1, mock_mbient_1, mock_Intel_1}')])

            table = Table('devices')
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

            table = Table('stimulus', conn_mock)
            table.insert_rows([('mock_test_1', 'description', 2, None,
                                'stream_python',
                                'tasks.test.mock_test.py::mock_stim()',
                                None, None)])


def delete_mock_rows():
    """Delete mock."""
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
            table_ids = ['study', 'collections', 'tech_obs_data', 'devices',
                         'sensors', 'stimulus']
            primary_keys = ['study_id', 'collection_id', 'tech_obs_id',
                            'device_id', 'sensor_id', 'stimulus_id']
            for table_id, pk in zip(table_ids, primary_keys):
                table = Table(table_id, conn_mock)
                table.delete_row(f'{pk} LIKE mock\%')


def test_neurobooth():
    """Call function to test neurobooth."""
    delete_mock_rows()
    create_mock_database()
    delete_mock_rows()
