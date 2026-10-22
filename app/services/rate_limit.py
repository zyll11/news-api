import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.exceptions import RateLimitError

logger = logging.getLogger(__name__)


class FailedAttemptLimiter:
    """Fixed-window counter of failed attempts stored in Redis.

    Fails open: if Redis is unavailable, login keeps working (availability is preferred
    here; the outage is logged).
    """

    def __init__(self, redis: Redis, limit: int, window_seconds: int, prefix: str) -> None:
        self.redis = redis
        self.limit = limit
        self.window = window_seconds
        self.prefix = prefix

    def _key(self, identity: str) -> str:
        return f"{self.prefix}:{identity}"

    async def check(self, identity: str) -> None:
        try:
            key = self._key(identity)
            attempts = int(await self.redis.get(key) or 0)
            if attempts >= self.limit:
                ttl = await self.redis.ttl(key)
                raise RateLimitError(retry_after=ttl if ttl > 0 else self.window)
        except RedisError:
            logger.warning("Rate limiter unavailable, skipping check", exc_info=True)

    async def register_failure(self, identity: str) -> None:
        try:
            key = self._key(identity)
            attempts = await self.redis.incr(key)
            if attempts == 1:
                await self.redis.expire(key, self.window)
        except RedisError:
            logger.warning("Rate limiter unavailable, failure not counted", exc_info=True)

    async def reset(self, identity: str) -> None:
        try:
            await self.redis.delete(self._key(identity))
        except RedisError:
            logger.warning("Rate limiter unavailable, reset skipped", exc_info=True)
