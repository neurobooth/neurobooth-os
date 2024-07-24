"""
Definitions of all inter-service messages.

Messages take the form of a Message instance, which includes a standard header in the form of a list of attributes
common to all message types, and a json body.  All messages are defined as pydantic models to ensure that they conform
to the desired structure. The body itself should be defined as a pydantic model, before being converted to json for
persistence.

Messaging is performed asynchronously with the database as an intermediary.
"""


from typing import List

from pydantic import BaseModel


class Message(BaseModel):
    guid: str       # Unique id for request
    name: str       # Name for request type
    source: str     # Server sending request (e.g. 'CTR')
    dest: str       # Server handling request (e.g. 'STM')
    sent: str       # Server time at request creation
    body: str       # Message body


class MsgBody(BaseModel):
    pass


class PrepareRequest(MsgBody):
    database_name: str
    subject_id: str
    session_id: int
    collection_id: str
    selected_tasks: List[str]
    date: str

    def session_name(self):
        return f'{self.subject_id}_{self.date}'


class TaskInfo(BaseModel):
    task_id: str
    stimulus_id: str
    task_start_time: str
    log_task_id: str


# TODO: Unused message type
class StatusMessage(BaseModel):
    text: str
