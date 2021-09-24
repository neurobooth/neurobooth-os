"""Add and delete rows from mock database."""

# Authors: Mainak Jas <mainakjas@gmail.com>

from neurobooth_terra import Table, list_tables, create_table


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

 
  # create mock inst row
   # parameters_dict =add a parameter json  
    table = Table('stimulus', conn_mock)
    table.insert_rows([('mock_test_1', 'description', 2, 5,                        
                        'mock.mock_task.py::simulated_task()', parameters_dict)],
                        cols=['stimulus_id', 'stimulus_description', 'num_iterations', "duration",
                         'stimulus_file', 'parameters'])

    # create mock inst row
   # instruction_id = Table('instruction', conn_mock).insert_rows([(7,)], cols=['instruction_id'])

    table = Table('tech_obs_data', conn_mock)
    table.insert_rows([('mock_obs', None, 'testing', None, instruction_id, None,
                        'mock_test_1',
                        '{mock_dev_1, mock_mbient_1, mock_Intel_1}',
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
    """Delete rows in mock database with primary key starting with mock.

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
