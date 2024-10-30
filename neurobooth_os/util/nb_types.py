from typing import Optional

from pydantic import BaseModel
from datetime import datetime


class Subject(BaseModel):
    subject_id: str
    first_name_birth: str
    middle_name_birth: str
    last_name_birth: str
    date_of_birth: datetime
    preferred_first_name: str
    preferred_last_name: str
