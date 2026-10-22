from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.user import UserPublic

CommentText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class CommentCreate(BaseModel):
    text: CommentText


class CommentUpdate(BaseModel):
    text: CommentText


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    news_id: int
    author: UserPublic
    created_at: datetime
    updated_at: datetime
