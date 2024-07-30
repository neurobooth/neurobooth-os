"""
Definitions of all inter-service messages.

Messages take the form of a Message instance, which includes a standard header in the form of a list of attributes
common to all message types, and a json body.  All messages are defined as pydantic models to ensure that they conform
to the desired structure. The body itself should be defined as a pydantic model, before being converted to json for
persistence.

Messaging is performed asynchronously with the database as an intermediary.
"""

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class MsgBody(BaseModel):
    pass


# TODO: Add string length constraints for source, destination, and type
class Message(BaseModel):
    uuid: str = uuid.uuid4()                    # Unique id for message
    type: str                                   # Name for request type
    source: str                                 # Service sending request (e.g. 'CTR')
    destination: str                            # List of services handling the request
    time_created: datetime = datetime.now()     # Time of message creation
    time_read: Optional[datetime] = None        # Time when message was read
    priority: int = 50                          # message priority, higher values move to front of queue
    body: MsgBody                               # Message body


class Request(Message):
    """
    A Message that is not issued in reply to any other message. Used to either start a conversation or for messages that
    require no reply. See also Reply
    """
    pass


class Reply(Message):
    request_uuid: str           # Unique id of message we are replying to


class PrepareRequest(MsgBody):
    database_name: str
    subject_id: str
    session_id: int
    collection_id: str
    selected_tasks: List[str]
    date: str

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
