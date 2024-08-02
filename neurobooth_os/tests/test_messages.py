import unittest
import neurobooth_os.iout.metadator as meta
from datetime import date

from neurobooth_os.msg.messages import Request, PrepareRequest

database_name = "mock_neurobooth"
dt = date.today()
body = PrepareRequest(database_name=database_name,
                      subject_id='100001',
                      session_id=12345,
                      collection_id='test_no_eyelink',
                      selected_tasks=['task_1'],
                      date=dt.isoformat())

msg = Request(
              source='CTR',
              destination='STM',
              body=body
)


class TestMessages(unittest.TestCase):

    def test_instantiation(self):
        print(body.model_dump_json() )
        print(msg.model_dump_json())

    def test_post(self):
        conn = meta.get_database_connection(database=database_name, validate_config_paths=False)
        meta.post_message(msg, conn)

    def test_read(self):
        conn = meta.get_database_connection(database=database_name, validate_config_paths=False)
        meta.post_message(msg, conn)
        message = meta.read_next_message(msg.destination, conn)
        print(message.model_dump_json())
        print(type(message.uuid))
