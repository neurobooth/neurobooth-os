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

from pydantic import BaseModel, SerializeAsAny

# Standard priority levels for messages, Higher priority messages are processed before lower priority messages
# If two messages have equal priorities, the one created first (based on Message_Queue table's ID column value)
# is processed first
HIGHEST_PRIORITY = 100
HIGH_PRIORITY = 75
MEDIUM_HIGH_PRIORITY = 65
MEDIUM_PRIORITY = 50
LOW_PRIORITY = 25


class MsgBody(BaseModel):
    """
    Superclass of all message bodies. This defines the content of the message
    """

    # These attributes are required, but should typically be set as constants in subclass init code,
    # rather than at Construction
    msg_type: Optional[str]
    module: Optional[str]
    priority: Optional[int]

    def __init__(self, **data):
        data['msg_type']=self.__class__.__name__
        data['module'] = self.__module__
        super().__init__(**data)


# TODO: Add string length constraints for source, destination, and type
class Message(BaseModel):
    """
    Superclass of all messages. Message defines the attributes shared by all message types
    """
    uuid: UUID = uuid4()                        # Unique id for message
    msg_type: Optional[str]                     # Filled-in automatically from the MsgBody subtype class name
    source: Optional[str]                       # Service sending request (e.g. 'CTR')
    destination: Optional[str]                  # Service handling the request
    time_created: Optional[datetime] = None     # Database server-time of message creation
    time_read: Optional[datetime] = None        # Database server-time when message was read
    priority: Optional[int]                     # message priority, filled-in automatically from MsgBody field
    body: Optional[SerializeAsAny[MsgBody]]     # Message body

    def __init__(self, **data: Any):
        super().__init__(**data)

    def full_msg_type(self) -> str:
        mod = self.body.module
        if mod.startswith("neurobooth_os."):
            mod = mod.replace("neurobooth_os.", '')
        return f"{mod}.py::{self.body.msg_type}()"


class Request(Message):
    """
    A standard message. Extracts type specific information from the message body and puts it in the message itself,
    so that it's easily queryable in the database.
    """
    def __init__(self, **data):
        body: MsgBody = data['body']
        data['msg_type'] = body.msg_type
        data['priority'] = body.priority
        super().__init__(**data)


class PrepareRequest(MsgBody):
    """
    Message sent from the controller to the backend services to tell them to connect all necessary devices
    """
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


class SessionPrepared(MsgBody):
    """
    Message sent to controller in reply to PrepareRequest to tell it that that preparation is complete
    """
    elem_key: str ="-Connect-"

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class CreateTasksRequest(MsgBody):
    """
    Message sent from controller to tell the stimulus server to create all necessary task and load their media
    """
    tasks: List[str]
    subj_id: str
    session_id: int
    frame_preview_device_id: Optional[str]  # The device used to perform automated frame previews for each task

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class TasksCreated(MsgBody):
    f"""
    Message sent to controller in reply to {CreateTasksRequest} to tell it that all necessary tasks were created along with their media
    """
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class ServerStarted(MsgBody):
    """
    Message sent from backend servers (e.g. ACQ, STM) to the controller to tell it they have started successfully
    """
    elem_key: str = "-init_servs-"

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class PerformTaskRequest(MsgBody):
    """
    Message sent from controller to STM to tell it to run the task named in its task_id attribute
    """
    task_id: str

    def __init__(self, **data):
        if "priority" not in data:
            data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class TasksFinished(MsgBody):
    """
    Message sent from controller to STM to tell it that all tasks have been performed and it should display the
    "Thank you for participating" message
    """
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class PauseSessionRequest(MsgBody):
    """
    Message from controller to STM telling it to pause. It is received by the backend after the currently executing task
     and before any remaining tasks due to its higher priority
    """
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
    f"""
    Message from controller to STM telling it to resume processing tasks. This message is only valid after a 
    {PauseSessionRequest} message.
    """
    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class StopSessionRequest(MsgBody):
    f"""
    Message from controller to STM telling it to stop processing tasks after the current task ends. 
    This message is issued after a {PauseSessionRequest} message or when the Stop button is pushed.
    """

    def __init__(self, **data):
        data['priority'] = HIGHEST_PRIORITY
        super().__init__(**data)


class TerminateServerRequest(MsgBody):
    f"""
    Message from controller to STM and ACQ telling them to shut down. This message is issued 
    when the Terminate Server button is pushed or if the GUI window is closed.
    """

    def __init__(self, **data):
        data['priority'] = HIGHEST_PRIORITY
        super().__init__(**data)


class CalibrationRequest(MsgBody):
    """
    Message sent from controller to STM to indicate that Eyetracker should be calibrated after the current task
    """
    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class DeviceInitialization(MsgBody):
    """
    Msg sent from Device modules to indicate that they've been initialized

    Note:
    auto_camera_preview should only be set to true for one device in a given session
    if more than one device has auto_camera_preview set to True, the one that will be used is undefined.
    if auto_camera preview is True, camera_preview must also be true or an exception is raised
    """
    stream_name: str
    outlet_id: str
    device_id: str = ''
    camera_preview: bool = False
    auto_camera_preview: bool = False # Is this the device for automated previews for each task?

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        if self.auto_camera_preview and not self.camera_preview:
            raise RuntimeError(f"Device configuration error for device {self.device_id}. auto_camera_preview "
                               f"set to True, but camera_preview is False.")
        super().__init__(**data)


class TaskInitialization(MsgBody):
    """
    Message sent from STM to CTR to tell CTR to start LSL
    """
    task_id: str
    log_task_id: str
    tsk_start_time: str

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class LslRecording(MsgBody):
    f"""
    Message sent from CTR to STM in response to a {TaskInitialization} message confirming that LSL recording has started
    """

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class TaskCompletion(MsgBody):
    """
    Message sent from STM to CTR to tell CTR to stop LSL
    """
    task_id: str
    has_lsl_stream: bool = True  # True if the task has associated LSL streams (False for instructions, pauses)

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class StatusMessage(MsgBody):
    """
    Message sent from backend servers to the controller with status information. The text is printed on the GUI
    """
    text: str
    status: Optional[str] = "INFO"

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class ErrorMessage(StatusMessage):
    """
    Message sent from backend servers to the controller with error information. The text is printed on the GUI
    """

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        if "status" not in data:
            data['status'] = "ERROR"
        super().__init__(**data)


class StartRecording(MsgBody):
    """
    Message sent from STM to ACQ telling it to start recording
    """
    fname: str
    task_id: str
    frame_preview_device_id: Optional[str] = None
    session_name: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class StartRecordingMsg(Request):
    """
    Convenience Request subclass. Sets the source and destination to be STM and ACQ to start recording task data
    """
    def __init__(self, **data):
        data['source'] = 'STM'
        data['destination'] = 'ACQ'
        super().__init__(**data)


class StopRecording(MsgBody):
    """
    Message sent from STM to ACQ telling it to stop recording LSL as the task being recorded has completed.
    """
    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class RecordingStarted(MsgBody):
    f"""
    Confirmation message sent from ACQ to STM in response to a {StartRecording} message
    """
    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class RecordingStopped(MsgBody):
    f"""
        Confirmation message sent from ACQ to STM in response to a {StopRecording} message
    """
    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class RecordingStoppedMsg(Request):
    f"""
    Specialized {Request} subclass wrapping a RecordingStopped {MsgBody}
    """
    def __init__(self, **data):
        data['source'] = 'ACQ'
        data['destination'] = 'STM'
        data['body'] = RecordingStopped()
        super().__init__(**data)


class RecordingStartedMsg(Request):
    f"""
    Specialized {Request} subclass wrapping a RecordingStarted {MsgBody}
    """
    def __init__(self, **data):
        data['source'] = 'ACQ'
        data['destination'] = 'STM'
        data['body'] = RecordingStarted()
        super().__init__(**data)


class ResetMbients(MsgBody):
    f"""
    Message sent from the mbient_reset module to ACQ requesting that the mbients be reset
    """

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class MbientResetResults(MsgBody):
    f"""
    Message sent from ACQ to STM in reply to a {ResetMbients} request containing the results from the reset
    """
    results: Dict[str, bool]

    def __init__(self, **data):
        data['priority'] = MEDIUM_HIGH_PRIORITY
        super().__init__(**data)


class FramePreviewRequest(MsgBody):
    """
    Message from controller to ACQ asking for a frame preview image from the specified device initiated by an RC
    through the GUI.
    """
    device_id: str

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class FramePreviewReply(MsgBody):
    f"""
    Message from ACQ to controller/gui in response to {FramePreviewRequest} containing an camera frame preview image
    """
    image: Optional[str] = None
    image_available: bool
    unavailable_message: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class MbientDisconnected(MsgBody):
    """
    Message sent from mbient device module to GUI indicating that an Mbient was disconnected
    """
    warning: str

    def __init__(self, **data):
        data['priority'] = MEDIUM_PRIORITY
        super().__init__(**data)


class NoEyetracker(MsgBody):
    """
    Message sent from Eyelink device module (eyelink_tracker.py) to indicate that the Eyetracker isn't running
    """
    warning: str

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)


class NewVideoFile(MsgBody):
    """
    Message sent by devices, or by the controller (for Marker streams) to indicate that a new VideoFile was created
    """
    event: str = "-new_filename-"
    stream_name: str
    filename: str

    def __init__(self, **data):
        data['priority'] = HIGH_PRIORITY
        super().__init__(**data)
