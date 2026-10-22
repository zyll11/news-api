from datetime import datetime
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def normalize_email(value: str) -> str:
    if len(value) > 255:
        raise ValueError("Email is too long")
    return value.lower()


class UserCreate(BaseModel):
    name: Name
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_lowercase(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Password must contain both letters and digits")
        return value


class UserUpdate(BaseModel):
    name: Name | None = None
    avatar: HttpUrl | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "UserUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one field must be provided")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class UserRolesUpdate(BaseModel):
    is_author: bool


class UserPublic(BaseModel):
    """Shape used when a user is embedded into other resources."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    avatar: str | None = None


class UserRead(UserPublic):
    email: EmailStr
    registered_at: datetime
    is_active: bool
    is_author: bool
    is_admin: bool
