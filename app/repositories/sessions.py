from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models import RefreshSession


class RefreshSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, session_id: int) -> RefreshSession | None:
        return await self.session.get(RefreshSession, session_id)

    async def get_by_token_hash(
        self, token_hash: str, *, for_update: bool = False
    ) -> RefreshSession | None:
        stmt = select(RefreshSession).where(RefreshSession.token_hash == token_hash)
        if for_update:
            # Serialises concurrent refreshes of the same token (no-op on SQLite).
            stmt = stmt.with_for_update()
        return await self.session.scalar(stmt)

    async def list_active_for_user(self, user_id: int) -> Sequence[RefreshSession]:
        stmt = (
            select(RefreshSession)
            .where(
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
                RefreshSession.expires_at > utcnow(),
            )
            .order_by(RefreshSession.created_at, RefreshSession.id)
        )
        return (await self.session.scalars(stmt)).all()

    def add(self, refresh_session: RefreshSession) -> None:
        self.session.add(refresh_session)

    async def revoke_all_for_user(self, user_id: int) -> None:
        await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
