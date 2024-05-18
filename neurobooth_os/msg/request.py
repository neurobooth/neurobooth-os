import datetime


from pydantic import BaseModel


class Request(BaseModel):
    id: str         # Unique id for request
    name: str       # Name for request type
    source: str     # Server sending request (e.g. 'CTR')
    dest: str       # Server handling request (e.g. 'STM')
    sent: datetime  # Server time at request creation
    body: str       # Message body
