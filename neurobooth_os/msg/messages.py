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
from typing import List, Optional, Any, Dict

from pydantic import BaseModel

# Standard priority levels for messages, Higher priority messages are processed before lower priority messages
# If two messages have equal priorities, the one created first (based on Message_Queue table's ID column value)
# is processed first
HIGHEST_PRIORITY = 100
HIGH_PRIORITY = 75
MEDIUM_HIGH_PRIORITY = 65
MEDIUM_PRIORITY = 50
LOW_PRIORITY = 25


class MsgBody(BaseModel):

    # These attributes are required, but should be set as constants in subclass init code, rather than at Construction
    msg_type: Optional[str]
    module: Optional[str]
    priority: Optional[int]

    def __init__(self, **data):
        data['msg_type']=self.__class__.__name__
        data['module'] = self.__module__
        super().__init__(**data)


# TODO: Add string length constraints for source, destination, and type
class Message(BaseModel):
    uuid: UUID = uuid4()                        # Unique id for message
    msg_type: Optional[str]                     # Filled-in automatically from the MsgBody subtype class name
    source: Optional[str]                       # Service sending request (e.g. 'CTR')
    destination: Optional[str]                  # Service handling the request
    time_created: datetime = datetime.now()     # Time of message creation
    time_read: Optional[datetime] = None        # Time when message was read
    priority: Optional[int]                     # message priority, filled-in automatically from MsgBody field
    body: Optional[MsgBody]                     # Message body

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
    request_uuid: UUID           # Unique id of message we are replying to

    def __init__(self, **data):
        body: MsgBody = data['body']
        data['msg_type'] = body.msg_type
        data['priority'] = body.priority
        super().__init__(**data)


class PrepareRequest(MsgBody):
    database_name: str
    subject_id: str
    collection_id: str
    selected_tasks: List[str]
    date: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)

    def session_name(self):
        return f'{self.subject_id}_{self.date}'


class TasksCreated(MsgBody):

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class SessionPrepared(MsgBody):
    elem_key: str ="-Connect-"

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class ServerStarted(MsgBody):
    elem_key: str = "-init_servs-"

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class CreateTasksRequest(MsgBody):
    tasks: List[str]
    subj_id: str
    session_id: int

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class PerformTaskRequest(MsgBody):
    task_id: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class TasksFinished(MsgBody):
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class PauseSessionRequest(MsgBody):

    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class CancelSessionRequest(MsgBody):
    """
    Request to cancel the remaining tasks in the session after the current task completes.
    Session must be paused, or have a pending PauseRequest queued, when this request is made
    """
    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class ResumeSessionRequest(MsgBody):

    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class StopSessionRequest(MsgBody):

    def __init__(self, **data):
        data['priority'] = HIGHEST_PRIORITY
        super().__init__(**data)


class TerminateServerRequest(MsgBody):

    def __init__(self, **data):
        data['priority'] = HIGHEST_PRIORITY
        super().__init__(**data)


class CalibrationRequest(MsgBody):

    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class DeviceInitialization(MsgBody):
    """
    Msg sent from Device modules to indicate that they've been initialized
    """
    stream_name: str
    outlet_id: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class LslRecording(MsgBody):
    """
    Msg sent from CTR to STM when LSL recording has started
    """
    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class TaskInitialization(MsgBody):
    """
    Msg sent from STM to CTR to tell CTR to start LSL
    """
    task_id: str
    log_task_id: str
    tsk_start_time: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class TaskCompletion(MsgBody):
    """
    Msg sent from STM to CTR to tell CTR to stop LSL
    """
    task_id: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class StatusMessage(MsgBody):
    text: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class StartRecording(MsgBody):
    fname: str
    task_id: str
    session_name: str
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class StartRecordingMsg(Request):
    """
    Request from STM to ACQ to start recording task data
    """
    def __init__(self, **data):
        data['source'] = 'STM'
        data['destination'] = 'ACQ'
        super().__init__(**data)


class StopRecording(MsgBody):
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class RecordingStarted(MsgBody):
    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class RecordingStopped(MsgBody):
    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class RecordingStoppedMsg(Reply):

    def __init__(self, **data):
        data['source'] = 'ACQ'
        data['destination'] = 'STM'
        data['body'] = RecordingStopped()
        super().__init__(**data)


class RecordingStartedMsg(Reply):

    def __init__(self, **data):
        data['source'] = 'ACQ'
        data['destination'] = 'STM'
        data['body'] = RecordingStarted()
        super().__init__(**data)


class ResetMbients(MsgBody):
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class MbientResetResults(MsgBody):
    results: Dict[str, bool]

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class FramePreviewRequest(MsgBody):
    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class FramePreviewReply(MsgBody):
    image: Optional[bytearray]
    image_available: bool

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITYF
        super().__init__(**data)


class MbientDisconnected(MsgBody):
    warning: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class NoEyetracker(MsgBody):
    warning: str

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class NewVideoFile(MsgBody):
    event: str
    stream_name: str
    filename: str

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)
