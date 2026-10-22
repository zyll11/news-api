"""Application factory. Run with: uvicorn app.main:create_app --factory"""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app import __version__
from app.api.routes import auth, comments, health, news, users
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import add_request_logging, configure_logging
from app.db.database import Database
from app.services.github import GitHubOAuthClient


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    redis: Redis | None = None,
    github_client: GitHubOAuthClient | None = None,
) -> FastAPI:
    """Build the app. Infrastructure can be injected (tests do that); anything not
    injected is created on startup and closed on shutdown."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cleanup: list[Callable[[], Awaitable[None]]] = []
        if app.state.db is None:
            app.state.db = Database(settings.database_url)
            cleanup.append(app.state.db.dispose)
        if app.state.redis is None:
            app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
            cleanup.append(app.state.redis.aclose)
        if app.state.github is None and settings.github_oauth_enabled:
            http = httpx.AsyncClient(timeout=10.0)
            app.state.github = GitHubOAuthClient(
                http,
                client_id=settings.github_client_id or "",
                client_secret=(
                    settings.github_client_secret.get_secret_value()
                    if settings.github_client_secret
                    else ""
                ),
            )
            cleanup.append(http.aclose)
        try:
            yield
        finally:
            for close in reversed(cleanup):
                await close()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="News portal API: JWT + refresh-token rotation, GitHub OAuth, RBAC, "
        "Redis caching.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = database
    app.state.redis = redis
    app.state.github = github_client

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    add_request_logging(app)
    register_exception_handlers(app)

    api = APIRouter(prefix="/api/v1")
    for module in (auth, users, news, comments):
        api.include_router(module.router)
    app.include_router(health.router)
    app.include_router(api)
    return app
