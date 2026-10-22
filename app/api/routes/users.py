from fastapi import APIRouter

from app.api.deps import AdminUser, CurrentUser, PaginationDep, UserServiceDep
from app.models import User
from app.schemas.common import ErrorResponse, Page
from app.schemas.user import UserRead, UserRolesUpdate, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(data: UserUpdate, user: CurrentUser, service: UserServiceDep) -> User:
    return await service.update_profile(user, data)


@router.get("", response_model=Page[UserRead], responses={403: {"model": ErrorResponse}})
async def list_users(
    _: AdminUser, pagination: PaginationDep, service: UserServiceDep
) -> Page[UserRead]:
    return await service.list(pagination)


@router.get(
    "/{user_id}",
    response_model=UserRead,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def read_user(user_id: int, user: CurrentUser, service: UserServiceDep) -> User:
    return await service.get(user, user_id)


@router.patch(
    "/{user_id}/roles",
    response_model=UserRead,
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def update_roles(
    user_id: int, data: UserRolesUpdate, _: AdminUser, service: UserServiceDep
) -> User:
    return await service.set_roles(user_id, data)
