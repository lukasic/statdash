import uuid
from datetime import datetime

from pydantic import BaseModel


class NoteCreate(BaseModel):
    source: str
    check_name: str
    host: str | None = None
    content: str


class NoteUpdate(BaseModel):
    content: str | None = None
    resolved: bool | None = None


class NoteRead(BaseModel):
    id: uuid.UUID
    source: str
    check_name: str
    host: str | None
    author: str
    content: str
    resolved: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
