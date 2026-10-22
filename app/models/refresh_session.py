from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utcnow
from app.db.base import Base


class RefreshSession(Base):
    """One login session. Stores only a SHA-256 hash of the refresh token."""

    __tablename__ = "refresh_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the token was exchanged for a new one. Presenting a rotated token again
    # means it leaked; a token revoked by logout is merely invalid.
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    @property
    def is_rotated(self) -> bool:
        return self.rotated_at is not None

    def __repr__(self) -> str:
        return f"<RefreshSession id={self.id} user_id={self.user_id}>"
