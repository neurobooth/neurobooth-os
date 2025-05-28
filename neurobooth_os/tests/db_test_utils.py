import unittest

from neurobooth_terra import Table
from neurobooth_os.iout.metadator import get_database_connection

TEST_DATABASE = "mock_neurobooth_1"
TEST_CONNECTION = None


def get_records(db_table, where=None):
    """Test utility for querying log_application table. Returns results as a dataframe"""
    table = Table(db_table, TEST_CONNECTION)
    if where is not None:
        task_df = table.query(where)
    else:
        task_df = table.query()
    return task_df


def delete_records(db_table, where=None) -> None:
    """Test utility for querying log_application table. Returns results as a dataframe"""
    table = Table(db_table, TEST_CONNECTION)
    if where is not None:
        table.delete_row(where)
    else:
        table.delete_row()


def get_connection():
    c = get_database_connection(TEST_DATABASE)
    c.autocommit = True
    return c


class TestLogging(unittest.TestCase):

    table = "log_application"

    def setUp(self):
        global TEST_CONNECTION
        if TEST_CONNECTION is not None:
            TEST_CONNECTION.close()
        TEST_CONNECTION = get_connection()
        delete_records(self.table)

    def test_get_records(self):
        """Meta-testing: Tests the get_records and delete_records utility function used in these tests"""
        df = get_records(self.table)
        assert(df is not None)
        delete_records(self.table)
        df = get_records(self.table)
        assert df.empty
