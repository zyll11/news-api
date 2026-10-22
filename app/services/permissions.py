"""Authorization rules kept in one place instead of being scattered across endpoints."""

from app.core.exceptions import PermissionDeniedError
from app.models import User


def can_publish(user: User) -> bool:
    return user.is_author or user.is_admin


def can_modify(user: User, owner_id: int) -> bool:
    return user.is_admin or user.id == owner_id


def ensure_can_modify(user: User, owner_id: int, what: str) -> None:
    if not can_modify(user, owner_id):
        raise PermissionDeniedError(f"You can only modify your own {what}")
