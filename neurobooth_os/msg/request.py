from typing import List

from pydantic import BaseModel


class Request(BaseModel):
    id: str         # Unique id for request
    name: str       # Name for request type
    source: str     # Server sending request (e.g. 'CTR')
    dest: str       # Server handling request (e.g. 'STM')
    sent: str       # Server time at request creation
    body: str       # Message body


class PrepareRequest(BaseModel):
    database_name: str
    subject_id: str
    session_id: int
    collection_id: str
    selected_tasks: List[str]
    date: str

    def session_name(self):
        return f'{self.subject_id}_{self.date}'
