from pydantic import BaseModel


class TextMessage(BaseModel):
    text: str
