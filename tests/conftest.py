"""Shared fixtures.

Tests run against in-memory SQLite by default (no services needed). Set TEST_DATABASE_URL
to a PostgreSQL URL to run the same suite against Postgres, as CI does.
Redis is replaced by fakeredis and GitHub by an httpx MockTransport.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable

import fakeredis
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.database import Database
from app.main import create_app
from app.models import User
from app.services.github import GitHubOAuthClient

PASSWORD = "Password123"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        environment="test",
        log_level="WARNING",
        database_url=TEST_DATABASE_URL,
        redis_url="redis://unused",
        jwt_secret="test-secret-that-is-long-enough-for-hs256-signing",
        login_rate_limit=3,
        max_sessions_per_user=3,
        github_client_id="test-client-id",
        github_client_secret="test-client-secret",
        public_base_url="http://testserver",
    )


@pytest_asyncio.fixture
async def database(settings: Settings) -> AsyncIterator[Database]:
    kwargs = {}
    if settings.database_url.startswith("sqlite"):
        kwargs = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    db = Database(settings.database_url, **kwargs)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield db
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await db.dispose()


@pytest.fixture
def redis_server() -> fakeredis.FakeServer:
    """Set `redis_server.connected = False` to simulate a Redis outage."""
    return fakeredis.FakeServer()


@pytest_asyncio.fixture
async def redis(redis_server: fakeredis.FakeServer) -> AsyncIterator[fakeredis.FakeAsyncRedis]:
    client = fakeredis.FakeAsyncRedis(server=redis_server, decode_responses=True)
    yield client
    redis_server.connected = True
    await client.flushall()
    await client.aclose()


class FakeGitHub:
    """Stands in for github.com and api.github.com."""

    def __init__(self) -> None:
        self.user = {
            "id": 4242,
            "login": "octocat",
            "name": "The Octocat",
            "avatar_url": "https://avatars.example.com/octocat",
        }
        self.emails = [{"email": "Octocat@Example.com", "primary": True, "verified": True}]

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/login/oauth/access_token":
            body = request.content.decode()
            if "code=good-code" in body:
                return httpx.Response(200, json={"access_token": "gh-token"})
            return httpx.Response(200, json={"error": "bad_verification_code"})
        if request.headers.get("Authorization") != "Bearer gh-token":
            return httpx.Response(401)
        if request.url.path == "/user":
            return httpx.Response(200, json=self.user)
        if request.url.path == "/user/emails":
            return httpx.Response(200, json=self.emails)
        return httpx.Response(404)


@pytest.fixture
def fake_github() -> FakeGitHub:
    return FakeGitHub()


@pytest_asyncio.fixture
async def app(
    settings: Settings,
    database: Database,
    redis: fakeredis.FakeAsyncRedis,
    fake_github: FakeGitHub,
) -> AsyncIterator[FastAPI]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(fake_github.handler)) as http:
        github = GitHubOAuthClient(http, "test-client-id", "test-client-secret")
        yield create_app(settings, database=database, redis=redis, github_client=github)


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


MakeUser = Callable[..., Awaitable[User]]


@pytest.fixture
def make_user(database: Database) -> MakeUser:
    async def _make(
        email: str = "user@example.com",
        *,
        name: str = "User",
        password: str | None = PASSWORD,
        is_author: bool = False,
        is_admin: bool = False,
        is_active: bool = True,
    ) -> User:
        async with database.sessionmaker() as session:
            user = User(
                name=name,
                email=email,
                hashed_password=hash_password(password) if password else None,
                is_author=is_author,
                is_admin=is_admin,
                is_active=is_active,
            )
            session.add(user)
            await session.commit()
            return user

    return _make


Login = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture
def login(client: httpx.AsyncClient) -> Login:
    async def _login(email: str, password: str = PASSWORD) -> dict[str, str]:
        resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.text
        return resp.json()

    return _login


def bearer(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest_asyncio.fixture
async def reader_headers(make_user: MakeUser, login: Login) -> dict[str, str]:
    await make_user("reader@example.com", name="Reader")
    return bearer(await login("reader@example.com"))


@pytest_asyncio.fixture
async def author_headers(make_user: MakeUser, login: Login) -> dict[str, str]:
    await make_user("author@example.com", name="Author", is_author=True)
    return bearer(await login("author@example.com"))


@pytest_asyncio.fixture
async def other_author_headers(make_user: MakeUser, login: Login) -> dict[str, str]:
    await make_user("author2@example.com", name="Author Two", is_author=True)
    return bearer(await login("author2@example.com"))


@pytest_asyncio.fixture
async def admin_headers(make_user: MakeUser, login: Login) -> dict[str, str]:
    await make_user("admin@example.com", name="Admin", is_admin=True)
    return bearer(await login("admin@example.com"))
