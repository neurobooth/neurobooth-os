from neurobooth_terra import Table
from neurobooth_os.iout.metadator import get_conn

TEST_DATABASE = "mock_neurobooth_1"
TEST_CONNECTION = None


def get_records(where=None):
    """Test utility for querying log_application table. Returns results as a dataframe"""
    table = Table("log_application", TEST_CONNECTION)
    if where is not None:
        task_df = table.query(where)
    else:
        task_df = table.query()
    return task_df


def delete_records(where=None) -> None:
    """Test utility for querying log_application table. Returns results as a dataframe"""
    table = Table("log_application", TEST_CONNECTION)
    if where is not None:
        table.delete_row(where)
    else:
        table.delete_row()


def get_connection():
    c = get_conn(TEST_DATABASE)
    c.autocommit = True
    return c


def test_get_records(self):
    """Meta-testing: Tests the get_records and delete_records utility function used in these tests"""
    df = get_records()
    assert(df is not None)
    delete_records()
    df = get_records()
    assert df.empty
