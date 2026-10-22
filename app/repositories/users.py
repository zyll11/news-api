from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return await self.session.scalar(stmt)

    async def get_by_oauth(self, provider: str, oauth_id: str) -> User | None:
        stmt = select(User).where(User.oauth_provider == provider, User.oauth_id == oauth_id)
        return await self.session.scalar(stmt)

    async def list(self, offset: int, limit: int) -> tuple[Sequence[User], int]:
        items = await self.session.scalars(
            select(User).order_by(User.id).offset(offset).limit(limit)
        )
        total = await self.session.scalar(select(func.count()).select_from(User))
        return items.all(), total or 0

    async def add(self, user: User) -> User:
        self.session.add(user)
        await self.session.flush()
        return user
