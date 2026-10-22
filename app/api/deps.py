"""FastAPI dependencies: database session, current user and service factories."""

from collections.abc import AsyncIterator
from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError, ServiceUnavailableError
from app.core.security import decode_access_token
from app.models import User
from app.repositories.users import UserRepository
from app.schemas.common import Pagination, pagination_params
from app.services.auth import AuthService
from app.services.cache import NewsCache
from app.services.comments import CommentService
from app.services.github import GitHubOAuthClient
from app.services.news import NewsService
from app.services.users import UserService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings  # type: ignore[no-any-return]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.db.sessionmaker() as session:
        yield session


SettingsDep = Annotated[Settings, Depends(get_settings)]
RedisDep = Annotated[Redis, Depends(get_redis)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
PaginationDep = Annotated[Pagination, Depends(pagination_params)]

_bearer = HTTPBearer(auto_error=False, description="Access token from /api/v1/auth/login")


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials, settings)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired access token") from exc
    user = await UserRepository(session).get(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise PermissionDeniedError("Administrator privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]


def get_auth_service(session: SessionDep, settings: SettingsDep, redis: RedisDep) -> AuthService:
    return AuthService(session, settings, redis)


def get_news_service(session: SessionDep, settings: SettingsDep, redis: RedisDep) -> NewsService:
    return NewsService(session, NewsCache(redis, settings.news_cache_ttl_seconds))


def get_comment_service(session: SessionDep) -> CommentService:
    return CommentService(session)


def get_user_service(session: SessionDep) -> UserService:
    return UserService(session)


def get_github_client(request: Request) -> GitHubOAuthClient:
    client: GitHubOAuthClient | None = request.app.state.github
    if client is None:
        raise ServiceUnavailableError("GitHub OAuth is not configured")
    return client


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
NewsServiceDep = Annotated[NewsService, Depends(get_news_service)]
CommentServiceDep = Annotated[CommentService, Depends(get_comment_service)]
UserServiceDep = Annotated[UserService, Depends(get_user_service)]
GitHubClientDep = Annotated[GitHubOAuthClient, Depends(get_github_client)]


def client_meta(request: Request) -> tuple[str | None, str | None]:
    """(user_agent, ip) of the caller, used to label login sessions."""
    ip = request.client.host if request.client else None
    return request.headers.get("user-agent"), ip
