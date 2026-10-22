"""Minimal GitHub OAuth client (authorization code flow)."""

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.exceptions import AuthenticationError, ServiceUnavailableError


@dataclass(frozen=True)
class GitHubProfile:
    id: str
    login: str
    name: str | None
    email: str
    avatar_url: str | None


class GitHubOAuthClient:
    AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    TOKEN_URL = "https://github.com/login/oauth/access_token"  # noqa: S105 - URL, not a secret
    API_URL = "https://api.github.com"
    SCOPE = "read:user user:email"

    def __init__(self, http: httpx.AsyncClient, client_id: str, client_secret: str) -> None:
        self.http = http
        self.client_id = client_id
        self.client_secret = client_secret

    def authorization_url(self, state: str, redirect_uri: str) -> str:
        query = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": redirect_uri,
                "scope": self.SCOPE,
                "state": state,
                "allow_signup": "true",
            }
        )
        return f"{self.AUTHORIZE_URL}?{query}"

    async def fetch_profile(self, code: str, redirect_uri: str) -> GitHubProfile:
        try:
            access_token = await self._exchange_code(code, redirect_uri)
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            }
            user_resp = await self.http.get(f"{self.API_URL}/user", headers=headers)
            user_resp.raise_for_status()
            emails_resp = await self.http.get(f"{self.API_URL}/user/emails", headers=headers)
            emails_resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ServiceUnavailableError("GitHub is unavailable, try again later") from exc

        user = user_resp.json()
        email = self._pick_verified_email(emails_resp.json())
        if email is None:
            raise AuthenticationError("GitHub account has no verified email address")
        return GitHubProfile(
            id=str(user["id"]),
            login=user["login"],
            name=user.get("name"),
            email=email.lower(),
            avatar_url=user.get("avatar_url"),
        )

    async def _exchange_code(self, code: str, redirect_uri: str) -> str:
        resp = await self.http.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if not token:
            # GitHub answers 200 with {"error": ...} for invalid or expired codes.
            raise AuthenticationError("GitHub authorization failed")
        return str(token)

    @staticmethod
    def _pick_verified_email(emails: list[dict[str, object]]) -> str | None:
        verified = [e for e in emails if e.get("verified")]
        primary = next((e for e in verified if e.get("primary")), None)
        chosen = primary or (verified[0] if verified else None)
        return str(chosen["email"]) if chosen else None
