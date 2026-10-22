from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.common import Page, Pagination
from app.schemas.user import UserRead, UserRolesUpdate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserRepository(session)

    async def get(self, requester: User, user_id: int) -> User:
        if requester.id != user_id and not requester.is_admin:
            raise PermissionDeniedError("You can only view your own profile")
        return await self._get_or_404(user_id)

    async def list(self, pagination: Pagination) -> Page[UserRead]:
        items, total = await self.repo.list(pagination.offset, pagination.limit)
        return Page[UserRead](
            items=[UserRead.model_validate(u) for u in items],
            total=total,
            offset=pagination.offset,
            limit=pagination.limit,
        )

    async def update_profile(self, user: User, data: UserUpdate) -> User:
        for field, value in data.model_dump(exclude_unset=True, mode="json").items():
            setattr(user, field, value)
        await self.session.commit()
        return user

    async def set_roles(self, user_id: int, data: UserRolesUpdate) -> User:
        user = await self._get_or_404(user_id)
        user.is_author = data.is_author
        await self.session.commit()
        return user

    async def _get_or_404(self, user_id: int) -> User:
        user = await self.repo.get(user_id)
        if user is None:
            raise NotFoundError("User not found")
        return user
