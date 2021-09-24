import psycopg2
from sshtunnel import SSHTunnelForwarder

from neurobooth_terra import Table, list_tables, create_table

# store stuff per table
table_dfs = dict()
column_names = dict()
dtypes = dict()

# Create an SSH tunnel
with SSHTunnelForwarder(
    'neurodoor.nmr.mgh.harvard.edu',
    ssh_username='an512',
    ssh_config_file='~/.ssh/config',
    ssh_pkey='~/.ssh/id_rsa',
    remote_bind_address=('192.168.100.1', 5432),
        local_bind_address=('localhost', 6543)) as tunnel:

    with psycopg2.connect(database='neurobooth', user='neuroboother',
                          password='neuroboothrocks', host=tunnel.local_bind_host,
                          port=tunnel.local_bind_port) as conn:

        table_ids = list_tables(conn)
        for table_id in table_ids:
            print(f'Table: {table_id}')
            table = Table(table_id, conn)
            table_dfs[table_id] = table.query(f'SELECT * from {table_id}')
            column_names[table_id] = table.column_names
            dtypes[table_id] = table.dtypes

    with psycopg2.connect(database='mock_neurobooth', user='neuroboother',
                          password='neuroboothrocks', host=tunnel.local_bind_host,
                          port=tunnel.local_bind_port) as conn_mock:
        for table_id in table_ids:
            create_table(table_id, conn, column_names[table_id],
                         dtypes[table_id])
