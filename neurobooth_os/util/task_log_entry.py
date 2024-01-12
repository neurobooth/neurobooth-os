from pydantic import BaseModel, NonNegativeInt
from typing import Optional, List


class TaskLogEntry(BaseModel):
    """
        Data-holder for task info to be logged
    """
    log_task_id: str = ''
    subject_id: str
    task_id: str
    log_session_id: Optional[NonNegativeInt] = None
    task_notes_file: str
    task_output_files: Optional[str]
    date_times: str
    event_array: List[str]
    subject_id_date: str

