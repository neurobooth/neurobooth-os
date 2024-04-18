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


def convert_to_array_literal(string_list:List[str], left_bracket: str = '{', right_bracket: str = '}'):
    # TODO(larry): Cleanup
    # (Brandon) Can probably replace with: '{' + ', '.join([f"'{s}'" for s in string_list]) + '}'
    """Converts the provided list of strings to a postgres array literal"""
    if string_list and isinstance(string_list, List):
        result: str = left_bracket
        size = len(string_list)
        i = 1

        for s in string_list:
            result += f'"{s}"'
            if i < size:
                result += ', '
                i += 1
        result += right_bracket
    elif string_list and isinstance(string_list, str):
        result = string_list
    else:
        result = left_bracket+right_bracket
    return result

