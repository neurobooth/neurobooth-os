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
    task_output_files: Optional[List[str]] = []
    date_times: str
    event_array: List[str]
    subject_id_date: str


def convert_to_array_literal(string_list: Optional[List[str]]):
    """Converts the provided list of strings to a postgres array literal"""
    result: str = "{"
    if string_list:
        size = len(string_list)
        i = 1

        for s in string_list:
            result += f"'{s}'"
            if i < size:
                result += ', '
                i += 1
        result += '}'
    else:
        result = '{}'
    return result

