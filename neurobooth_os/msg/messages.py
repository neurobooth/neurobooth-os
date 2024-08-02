"""
Definitions of all inter-service messages.

Messages take the form of a Message instance, which includes a standard header in the form of a list of attributes
common to all message types, and a json body.  All messages are defined as pydantic models to ensure that they conform
to the desired structure. The body itself should be defined as a pydantic model, before being converted to json for
persistence.

Messaging is performed asynchronously with the database as an intermediary.
"""

from uuid import uuid4, UUID
from datetime import datetime
from typing import List, Optional, Any

from pydantic import BaseModel


class MsgBody(BaseModel):
    msg_type: str
    module: str
    priority: int

    def __init__(self, **data):
        data['msg_type']=self.__class__.__name__
        data['module'] = self.__module__
        super().__init__(**data)


# TODO: Add string length constraints for source, destination, and type
class Message(BaseModel):
    uuid: UUID = uuid4()                   # Unique id for message
    msg_type: str                               # Name for request type
    source: str                                 # Service sending request (e.g. 'CTR')
    destination: str                            # List of services handling the request
    time_created: datetime = datetime.now()     # Time of message creation
    time_read: Optional[datetime] = None        # Time when message was read
    priority: int                               # message priority, higher values move to front of queue
    body: MsgBody                               # Message body

    def __init__(self, **data: Any):
        super().__init__(**data)

    def full_msg_type(self) -> str:
        mod = self.body.module
        if mod.startswith("neurobooth_os."):
            mod = mod.replace("neurobooth_os.", '')
        return f"{mod}.py::{self.body.msg_type}()"




class Request(Message):
    """
    A Message that is not issued in reply to any other message. Used to either start a conversation or for messages that
    require no reply. See also Reply
    """
    def __init__(self, **data):
        body: MsgBody = data['body']
        data['msg_type'] = body.msg_type
        data['priority'] = body.priority
        super().__init__(**data)


class Reply(Message):
    request_uuid: str           # Unique id of message we are replying to

    def __init__(self, **data):
        body: MsgBody = data['body']
        data['msg_type'] = body.msg_type
        data['priority'] = body.priority
        super().__init__(**data)


class PrepareRequest(MsgBody):
    database_name: str
    subject_id: str
    session_id: int
    collection_id: str
    selected_tasks: List[str]
    date: str

    def __init__(self, **data):
        data['priority'] = 50
        super().__init__(**data)

    def session_name(self):
        return f'{self.subject_id}_{self.date}'


class TaskInfo(MsgBody):
    task_id: str
    stimulus_id: str
    task_start_time: str
    log_task_id: str


# TODO: Unused message type
class StatusMessage(BaseModel):
    text: str
