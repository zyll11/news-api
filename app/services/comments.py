from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models import Comment, User
from app.repositories.comments import CommentRepository
from app.repositories.news import NewsRepository
from app.schemas.comment import CommentCreate, CommentRead, CommentUpdate
from app.schemas.common import Page, Pagination
from app.services.permissions import ensure_can_modify


class CommentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CommentRepository(session)
        self.news = NewsRepository(session)

    async def list_for_news(self, news_id: int, pagination: Pagination) -> Page[CommentRead]:
        await self._ensure_news_exists(news_id)
        items, total = await self.repo.list_for_news(news_id, pagination.offset, pagination.limit)
        return Page[CommentRead](
            items=[CommentRead.model_validate(c) for c in items],
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def create(self, author: User, news_id: int, data: CommentCreate) -> Comment:
        await self._ensure_news_exists(news_id)
        comment = await self.repo.add(Comment(text=data.text, news_id=news_id, author=author))
        await self.session.commit()
        return comment

    async def update(self, user: User, comment_id: int, data: CommentUpdate) -> Comment:
        comment = await self._get_or_404(comment_id)
        ensure_can_modify(user, comment.author_id, "comments")
        comment.text = data.text
        await self.session.commit()
        return comment

    async def delete(self, user: User, comment_id: int) -> None:
        comment = await self._get_or_404(comment_id)
        ensure_can_modify(user, comment.author_id, "comments")
        await self.repo.delete(comment)
        await self.session.commit()

    async def _ensure_news_exists(self, news_id: int) -> None:
        if not await self.news.exists(news_id):
            raise NotFoundError("News not found")

    async def _get_or_404(self, comment_id: int) -> Comment:
        comment = await self.repo.get(comment_id)
        if comment is None:
            raise NotFoundError("Comment not found")
        return comment
