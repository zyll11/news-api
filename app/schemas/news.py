from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.schemas.user import UserPublic

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class NewsCreate(BaseModel):
    title: Title
    content: dict[str, Any]
    cover_image: HttpUrl | None = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("content must not be empty")
        return value


class NewsUpdate(BaseModel):
    title: Title | None = None
    content: dict[str, Any] | None = None
    cover_image: HttpUrl | None = None

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is not None and not value:
            raise ValueError("content must not be empty")
        return value

    @model_validator(mode="after")
    def check_fields(self) -> "NewsUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        for field in ("title", "content"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class NewsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: dict[str, Any]
    cover_image: str | None
    author: UserPublic
    created_at: datetime
    updated_at: datetime
