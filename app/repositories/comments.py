from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Comment


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, comment_id: int) -> Comment | None:
        return await self.session.get(Comment, comment_id)

    async def list_for_news(
        self, news_id: int, offset: int, limit: int
    ) -> tuple[Sequence[Comment], int]:
        items = await self.session.scalars(
            select(Comment)
            .where(Comment.news_id == news_id)
            .order_by(Comment.created_at, Comment.id)
            .offset(offset)
            .limit(limit)
        )
        total = await self.session.scalar(
            select(func.count()).select_from(Comment).where(Comment.news_id == news_id)
        )
        return items.all(), total or 0

    async def add(self, comment: Comment) -> Comment:
        self.session.add(comment)
        await self.session.flush()
        return comment

    async def delete(self, comment: Comment) -> None:
        await self.session.delete(comment)
