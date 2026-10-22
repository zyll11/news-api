from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import News


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, news_id: int) -> News | None:
        return await self.session.get(News, news_id)

    async def exists(self, news_id: int) -> bool:
        return (await self.session.scalar(select(News.id).where(News.id == news_id))) is not None

    async def list(self, offset: int, limit: int) -> tuple[Sequence[News], int]:
        stmt = (
            select(News)
            .order_by(News.created_at.desc(), News.id.desc())
            .offset(offset)
            .limit(limit)
        )
        items = await self.session.scalars(stmt)
        total = await self.session.scalar(select(func.count()).select_from(News))
        return items.all(), total or 0

    async def add(self, news: News) -> News:
        self.session.add(news)
        await self.session.flush()
        return news

    async def delete(self, news: News) -> None:
        await self.session.delete(news)
