from typing import Any

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.user import User


class News(TimestampMixin, Base):
    __tablename__ = "news"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    cover_image: Mapped[str | None] = mapped_column(String(500))
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # Always needed in responses, so load it in the same query.
    author: Mapped[User] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return f"<News id={self.id}>"
