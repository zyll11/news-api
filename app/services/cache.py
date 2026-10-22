import logging

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.schemas.common import Page
from app.schemas.news import NewsRead

logger = logging.getLogger(__name__)

NewsPage = Page[NewsRead]


class NewsCache:
    """Read-through cache for news.

    Single items are cached by id. List pages are cached under a version number:
    any write bumps the version, which invalidates every cached page at once
    without having to scan keys. Redis errors never break a request.
    """

    VERSION_KEY = "news:list:version"

    def __init__(self, redis: Redis, ttl_seconds: int) -> None:
        self.redis = redis
        self.ttl = ttl_seconds

    @staticmethod
    def _item_key(news_id: int) -> str:
        return f"news:item:{news_id}"

    async def _page_key(self, offset: int, limit: int) -> str:
        version = await self.redis.get(self.VERSION_KEY) or "0"
        return f"news:list:v{version}:{offset}:{limit}"

    async def get_item(self, news_id: int) -> NewsRead | None:
        try:
            raw = await self.redis.get(self._item_key(news_id))
            return NewsRead.model_validate_json(raw) if raw else None
        except (RedisError, ValidationError):
            logger.warning("News cache read failed", exc_info=True)
            return None

    async def set_item(self, news: NewsRead) -> None:
        try:
            await self.redis.set(self._item_key(news.id), news.model_dump_json(), ex=self.ttl)
        except RedisError:
            logger.warning("News cache write failed", exc_info=True)

    async def get_page(self, offset: int, limit: int) -> NewsPage | None:
        try:
            raw = await self.redis.get(await self._page_key(offset, limit))
            return NewsPage.model_validate_json(raw) if raw else None
        except (RedisError, ValidationError):
            logger.warning("News cache read failed", exc_info=True)
            return None

    async def set_page(self, page: NewsPage) -> None:
        try:
            key = await self._page_key(page.offset, page.limit)
            await self.redis.set(key, page.model_dump_json(), ex=self.ttl)
        except RedisError:
            logger.warning("News cache write failed", exc_info=True)

    async def invalidate(self, news_id: int | None = None) -> None:
        try:
            if news_id is not None:
                await self.redis.delete(self._item_key(news_id))
            await self.redis.incr(self.VERSION_KEY)
        except RedisError:
            logger.warning("News cache invalidation failed", exc_info=True)
