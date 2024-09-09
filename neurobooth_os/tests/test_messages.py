import unittest
import neurobooth_os.iout.metadator as meta
from datetime import date, datetime

from neurobooth_os.msg.messages import Request, PrepareRequest, CreateTasksRequest, PerformTaskRequest, \
    MbientResetResults

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

conn = meta.get_database_connection(database=database_name, validate_config_paths=False)


class TestMessages(unittest.TestCase):

    def test_msg_read(self):

        body_1 = MbientResetResults(
            results={"Mbient_LH_2": True}
        )
        msg_1 = Request(
            source='ACQ',
            destination='STM',
            body=body_1
        )

        meta.post_message(msg_1, conn)
        message = meta.read_next_message(msg.destination, conn, msg_type='MbientResetResults')
        print(message.model_dump_json())
        print(type(message.uuid))


    def test_instantiation(self):
        print(body.model_dump_json())
        print(msg.model_dump_json())

    def test_post(self):
        meta.post_message(msg, conn)

    def test_read(self):
        meta.post_message(msg, conn)
        message = meta.read_next_message(msg.destination, conn)
        print(message.model_dump_json())
        print(type(message.uuid))

    def test_create_task_request(self):
        task_id: str = "12345"
        body_1 = CreateTasksRequest(task_id=task_id)
        msg_1 = Request(
            source='CTR',
            destination='STM',
            body=body_1
        )

        meta.post_message(msg_1, conn)
        message = meta.read_next_message(msg_1.destination, conn)
        self.assertEquals(str(msg_1.uuid), str(message.uuid))
        self.assertEquals(msg_1.body.task_id, message.body.task_id)

    def test_perform_task_request(self):
        task_id: str = "ahh_obs_1"
        stim_id: str = "ahhh_task_1"
        start_time: str = datetime.now().isoformat()
        log_task_id: str = "12345"
        body_1 = PerformTaskRequest(
            task_id=task_id,
            stimulus_id=stim_id,
            task_start_time=start_time,
            log_task_id=log_task_id
        )
        msg_1 = Request(
            source='CTR',
            destination='STM',
            body=body_1
        )

        meta.post_message(msg_1, conn)
        message = meta.read_next_message(msg_1.destination, conn)
        self.assertEquals(stim_id, message.body.stimulus_id)
        self.assertEquals(task_id, message.body.task_id)
        self.assertEquals(log_task_id, message.body.log_task_id)
        self.assertEquals(start_time, message.body.task_start_time)
        print(message.body.model_dump_json())
