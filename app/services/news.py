from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models import News, User
from app.repositories.news import NewsRepository
from app.schemas.common import Page, Pagination
from app.schemas.news import NewsCreate, NewsRead, NewsUpdate
from app.services.cache import NewsCache
from app.services.permissions import can_publish, ensure_can_modify


class NewsService:
    def __init__(self, session: AsyncSession, cache: NewsCache) -> None:
        self.session = session
        self.repo = NewsRepository(session)
        self.cache = cache

    async def list(self, pagination: Pagination) -> Page[NewsRead]:
        cached = await self.cache.get_page(pagination.offset, pagination.limit)
        if cached is not None:
            return cached
        items, total = await self.repo.list(pagination.offset, pagination.limit)
        page = Page[NewsRead](
            items=[NewsRead.model_validate(n) for n in items],
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )
        await self.cache.set_page(page)
        return page

    async def get(self, news_id: int) -> NewsRead:
        cached = await self.cache.get_item(news_id)
        if cached is not None:
            return cached
        result = NewsRead.model_validate(await self._get_or_404(news_id))
        await self.cache.set_item(result)
        return result

    async def create(self, author: User, data: NewsCreate) -> NewsRead:
        if not can_publish(author):
            raise PermissionDeniedError("Only verified authors can publish news")
        news = News(
            title=data.title,
            content=data.content,
            cover_image=str(data.cover_image) if data.cover_image else None,
            author=author,
        )
        await self.repo.add(news)
        await self.session.commit()
        await self.cache.invalidate()
        return NewsRead.model_validate(news)

    async def update(self, user: User, news_id: int, data: NewsUpdate) -> NewsRead:
        news = await self._get_or_404(news_id)
        ensure_can_modify(user, news.author_id, "news")
        for field, value in data.model_dump(exclude_unset=True, mode="json").items():
            setattr(news, field, value)
        await self.session.commit()
        await self.cache.invalidate(news_id)
        return NewsRead.model_validate(news)

    async def delete(self, user: User, news_id: int) -> None:
        news = await self._get_or_404(news_id)
        ensure_can_modify(user, news.author_id, "news")
        await self.repo.delete(news)
        await self.session.commit()
        await self.cache.invalidate(news_id)

    async def _get_or_404(self, news_id: int) -> News:
        news = await self.repo.get(news_id)
        if news is None:
            raise NotFoundError("News not found")
        return news
