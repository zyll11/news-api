from collections.abc import Sequence

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import AuthServiceDep, CurrentUser, GitHubClientDep, SettingsDep, client_meta
from app.models import RefreshSession, User
from app.schemas.auth import LoginRequest, RefreshRequest, SessionRead, TokenPair
from app.schemas.common import ErrorResponse
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["auth"])

_auth_errors: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def register(data: UserCreate, service: AuthServiceDep) -> User:
    return await service.register(data)


@router.post("/login", response_model=TokenPair, responses=_auth_errors)
async def login(data: LoginRequest, request: Request, service: AuthServiceDep) -> TokenPair:
    user_agent, ip = client_meta(request)
    return await service.login(data.email, data.password, user_agent=user_agent, ip=ip)


@router.post("/refresh", response_model=TokenPair, responses=_auth_errors)
async def refresh(data: RefreshRequest, request: Request, service: AuthServiceDep) -> TokenPair:
    user_agent, ip = client_meta(request)
    return await service.refresh(data.refresh_token, user_agent=user_agent, ip=ip)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: RefreshRequest, service: AuthServiceDep) -> Response:
    await service.logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUser, service: AuthServiceDep) -> Response:
    await service.logout_everywhere(user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(user: CurrentUser, service: AuthServiceDep) -> Sequence[RefreshSession]:
    return await service.list_sessions(user)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorResponse}},
)
async def revoke_session(session_id: int, user: CurrentUser, service: AuthServiceDep) -> Response:
    await service.revoke_session(user, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/github/login", status_code=status.HTTP_302_FOUND, responses={503: {"model": ErrorResponse}}
)
async def github_login(
    github: GitHubClientDep, service: AuthServiceDep, settings: SettingsDep
) -> RedirectResponse:
    state = await service.create_oauth_state()
    return RedirectResponse(
        github.authorization_url(state, settings.github_redirect_uri),
        status_code=status.HTTP_302_FOUND,
    )


@router.get(
    "/github/callback",
    response_model=TokenPair,
    responses={400: {"model": ErrorResponse}, 401: {"model": ErrorResponse}},
)
async def github_callback(
    code: str,
    state: str,
    request: Request,
    github: GitHubClientDep,
    service: AuthServiceDep,
    settings: SettingsDep,
) -> TokenPair:
    await service.consume_oauth_state(state)
    profile = await github.fetch_profile(code, settings.github_redirect_uri)
    user_agent, ip = client_meta(request)
    return await service.login_with_github(profile, user_agent=user_agent, ip=ip)
