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
    table.insert_rows([('mock_study', 'mock_study', '{mock_collection}', 0)],
                        cols=['study_id', 'study_title', 'collection_ids', 'IRB_protocol_number'])

    table = Table('collection', conn_mock)
    table.insert_rows([('mock_collection', '{mock_obs_1}')],
                      cols=['collection_id', 'tech_obs_array'])

    table = Table('stimulus', conn_mock)
    table.insert_rows([('mock_task_1', 'description', 2, 5,                        
                        'mock.mock_task.py::MockTask()', 'mp4')],
                        cols=['stimulus_id', 'stimulus_description', 'num_iterations', "duration",
                         'stimulus_file', 'stimulus_filetype'])

    Table('instruction', conn_mock).insert_rows(
        [('mock_instruction_id', "mock task, follow the instructions",)],
        cols=['instruction_id', 'instruction_text'])

    table = Table('tech_obs_data', conn_mock)
    table.insert_rows([('mock_obs_1', 'mock_instruction_id', 'mock_task_1',
                        '{mock_Mbient_1,mock_Mbient_2, mock_Intel_1}',                        
                        ('{{mock_Mbient_acc_1, mock_Mbient_grad_1},'
                         '{mock_Mbient_acc_1, mock_Mbient_grad_1},'
                         '{mock_Intel_rgb_1, mock_Intel_depth_1}}')
                         , "hand")], 
                         cols=["tech_obs_id", "instruction_id", "stimulus_id", "device_id_array",
                          "sensor_id_array", "feature_of_interest" ])

    table = Table('device', conn_mock)
    cols = ['device_id', 'device_sn', 'wearable_bool', 'device_location',
            'device_name', 'device_make', 'device_model', 'device_firmware',
            'sensor_id_array']
    table.insert_rows([('mock_dev_1', 0, False, 0, 'mock', 'mock_make',
                        'neurobooth inc', 0, '{mock_sens_1}')], cols=cols)
    table.insert_rows([('mock_Mbient_1', 0, False, 0, 'mock',
                        'mock_make', 'neurobooth inc', 0,
                        '{mock_Mbient_acc_1, mock_Mbient_grad_1}')], cols=cols)
    table.insert_rows([('mock_Mbient_2', 0, False, 0, 'mock',
                        'mock_make', 'neurobooth inc', 0,
                        '{mock_Mbient_acc_1, mock_Mbient_grad_1}')], cols=cols)
    table.insert_rows([('mock_Intel_1', 0, False, 0, 'mock',
                        'mock_make', 'neurobooth inc', 0,
                        '{mock_Intel_rgb_1, mock_Intel_depth_1}')], cols=cols)

    table = Table('sensor', conn_mock)
    cols = ['sensor_id', 'temporal_res', 'spatial_res_x', 'spatial_res_y',
            'file_type', 'laterality']
    table.insert_rows([('mock_sens_1', 100, None, None, 'edf', None)], cols=cols)
    table.insert_rows([('mock_Mbient_acc_1', 100, None, None, 'edf', None)], cols=cols)
    table.insert_rows([('mock_Mbient_grad_1', 100, None, None, 'edf', None)], cols=cols)
    table.insert_rows([('mock_Intel_rgb_1', 180, 1080, 720, 'bag', None)], cols=cols)
    table.insert_rows([('mock_Intel_depth_1', 180, 1080, 720, 'bag', None)], cols=cols)


def delete_mock_rows(conn_mock):
    """Delete rows in mock database with primary key starting with mock.

    Parameters
    ----------
    conn_mock : instance of psychopg2.connection
        The connection object to the mock database.
    """
    table_ids = ['study', 'collection', 'tech_obs_data', 'device',
                    'sensor', 'stimulus', 'instruction']
    primary_keys = ['study_id', 'collection_id', 'tech_obs_id',
                    'device_id', 'sensor_id', 'stimulus_id', 'instruction_id']
    for table_id, pk in zip(table_ids, primary_keys):
        table = Table(table_id, conn_mock)
        table.delete_row(f"{pk} LIKE 'mock%'")
