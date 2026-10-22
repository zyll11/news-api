import logging
import secrets
from collections.abc import Sequence
from datetime import timedelta

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_password,
)
from app.core.time import as_utc, utcnow
from app.models import RefreshSession, User
from app.repositories.sessions import RefreshSessionRepository
from app.repositories.users import UserRepository
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate
from app.services.github import GitHubProfile
from app.services.rate_limit import FailedAttemptLimiter

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid email or password"
OAUTH_STATE_TTL_SECONDS = 600


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings, redis: Redis) -> None:
        self.session = session
        self.settings = settings
        self.redis = redis
        self.users = UserRepository(session)
        self.sessions = RefreshSessionRepository(session)
        self.login_limiter = FailedAttemptLimiter(
            redis,
            limit=settings.login_rate_limit,
            window_seconds=settings.login_rate_window_seconds,
            prefix="ratelimit:login",
        )

    # --- Registration and password login -------------------------------------------------

    async def register(self, data: UserCreate) -> User:
        if await self.users.get_by_email(data.email):
            raise ConflictError("Email already registered")
        user = User(name=data.name, email=data.email, hashed_password=hash_password(data.password))
        try:
            await self.users.add(user)
            await self.session.commit()
        except IntegrityError as exc:  # concurrent registration with the same email
            await self.session.rollback()
            raise ConflictError("Email already registered") from exc
        return user

    async def login(
        self, email: str, password: str, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        limiter_key = f"{ip or 'unknown'}:{email}"
        await self.login_limiter.check(limiter_key)

        user = await self.users.get_by_email(email)
        # verify_password runs even for unknown users, so response time does not leak
        # whether the email exists.
        if not verify_password(password, user.hashed_password if user else None) or user is None:
            await self.login_limiter.register_failure(limiter_key)
            raise AuthenticationError(INVALID_CREDENTIALS)
        if not user.is_active:
            raise PermissionDeniedError("Account is disabled")

        await self.login_limiter.reset(limiter_key)
        if user.hashed_password and password_needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)
        return await self.issue_tokens(user, user_agent=user_agent, ip=ip)

    # --- Token lifecycle ------------------------------------------------------------------

    async def issue_tokens(
        self, user: User, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        """Create a new refresh session, evicting the oldest ones above the per-user limit."""
        active = await self.sessions.list_active_for_user(user.id)
        overflow = len(active) - self.settings.max_sessions_per_user + 1
        now = utcnow()
        for old in active[: max(overflow, 0)]:
            old.revoked_at = now

        refresh_token = generate_refresh_token()
        self.sessions.add(
            RefreshSession(
                user_id=user.id,
                token_hash=hash_token(refresh_token),
                user_agent=user_agent[:255] if user_agent else None,
                ip_address=ip,
                expires_at=now + timedelta(days=self.settings.refresh_token_ttl_days),
            )
        )
        await self.session.commit()
        return TokenPair(
            access_token=create_access_token(user.id, self.settings),
            refresh_token=refresh_token,
            expires_in=self.settings.access_token_ttl_minutes * 60,
        )

    async def refresh(
        self, refresh_token: str, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        """Rotate the refresh token. Reusing an already rotated token revokes every session,
        because it means the token was most likely stolen."""
        current = await self.sessions.get_by_token_hash(hash_token(refresh_token), for_update=True)
        if current is None:
            raise AuthenticationError("Invalid refresh token")

        if current.is_rotated:
            await self.sessions.revoke_all_for_user(current.user_id)
            await self.session.commit()
            logger.warning("Refresh token reuse detected for user_id=%s", current.user_id)
            raise AuthenticationError("Refresh token reuse detected, all sessions were revoked")

        if current.is_revoked:
            raise AuthenticationError("Invalid refresh token")

        if as_utc(current.expires_at) <= utcnow():
            current.revoked_at = utcnow()
            await self.session.commit()
            raise AuthenticationError("Refresh token expired")

        user = await self.users.get(current.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Invalid refresh token")

        now = utcnow()
        current.revoked_at = now
        current.rotated_at = now
        return await self.issue_tokens(user, user_agent=user_agent, ip=ip)

    async def logout(self, refresh_token: str) -> None:
        """Idempotent: an unknown or already revoked token is not an error."""
        current = await self.sessions.get_by_token_hash(hash_token(refresh_token))
        if current is not None and not current.is_revoked:
            current.revoked_at = utcnow()
            await self.session.commit()

    async def logout_everywhere(self, user: User) -> None:
        await self.sessions.revoke_all_for_user(user.id)
        await self.session.commit()

    async def list_sessions(self, user: User) -> Sequence[RefreshSession]:
        return await self.sessions.list_active_for_user(user.id)

    async def revoke_session(self, user: User, session_id: int) -> None:
        target = await self.sessions.get(session_id)
        if target is None or target.user_id != user.id:
            raise NotFoundError("Session not found")
        if not target.is_revoked:
            target.revoked_at = utcnow()
            await self.session.commit()

    # --- GitHub OAuth ---------------------------------------------------------------------

    async def create_oauth_state(self) -> str:
        """Random CSRF state stored in Redis and checked once in the callback."""
        state = secrets.token_urlsafe(32)
        try:
            await self.redis.set(f"oauth:state:{state}", "1", ex=OAUTH_STATE_TTL_SECONDS)
        except RedisError as exc:
            raise ServiceUnavailableError("Login via GitHub is temporarily unavailable") from exc
        return state

    async def consume_oauth_state(self, state: str) -> None:
        try:
            stored = await self.redis.getdel(f"oauth:state:{state}")
        except RedisError as exc:
            raise ServiceUnavailableError("Login via GitHub is temporarily unavailable") from exc
        if stored is None:
            raise BadRequestError("Invalid or expired OAuth state")

    async def login_with_github(
        self, profile: GitHubProfile, *, user_agent: str | None, ip: str | None
    ) -> TokenPair:
        user = await self.users.get_by_oauth("github", profile.id)
        if user is None:
            # GitHub confirmed ownership of this email, so it is safe to link the accounts.
            user = await self.users.get_by_email(profile.email)
            if user is None:
                user = await self.users.add(
                    User(
                        name=(profile.name or profile.login)[:100],
                        email=profile.email,
                        avatar=profile.avatar_url,
                        oauth_provider="github",
                        oauth_id=profile.id,
                    )
                )
            elif user.oauth_provider is None:
                user.oauth_provider = "github"
                user.oauth_id = profile.id
            else:
                raise ConflictError("This email is already linked to another external account")
        if not user.is_active:
            raise PermissionDeniedError("Account is disabled")
        return await self.issue_tokens(user, user_agent=user_agent, ip=ip)
