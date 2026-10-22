from urllib.parse import parse_qs, urlparse

import fakeredis
import httpx

from tests.conftest import FakeGitHub, MakeUser, bearer

API = "/api/v1"


async def start_login(client: httpx.AsyncClient) -> str:
    resp = await client.get(f"{API}/auth/github/login")
    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    query = parse_qs(location.query)
    assert location.netloc == "github.com"
    assert query["client_id"] == ["test-client-id"]
    assert query["redirect_uri"] == ["http://testserver/api/v1/auth/github/callback"]
    return query["state"][0]


async def test_login_redirects_to_github_and_stores_state(
    client: httpx.AsyncClient, redis: fakeredis.FakeAsyncRedis
) -> None:
    state = await start_login(client)
    assert await redis.get(f"oauth:state:{state}") == "1"
    assert await redis.ttl(f"oauth:state:{state}") > 0


async def test_callback_creates_user_and_issues_tokens(client: httpx.AsyncClient) -> None:
    state = await start_login(client)
    resp = await client.get(
        f"{API}/auth/github/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 200, resp.text
    me = (await client.get(f"{API}/users/me", headers=bearer(resp.json()))).json()
    assert me["email"] == "octocat@example.com"
    assert me["name"] == "The Octocat"
    assert me["is_author"] is False


async def test_state_is_single_use(client: httpx.AsyncClient) -> None:
    state = await start_login(client)
    params = {"code": "good-code", "state": state}
    assert (await client.get(f"{API}/auth/github/callback", params=params)).status_code == 200
    replay = await client.get(f"{API}/auth/github/callback", params=params)
    assert replay.status_code == 400


async def test_forged_state_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.get(
        f"{API}/auth/github/callback", params={"code": "good-code", "state": "forged"}
    )
    assert resp.status_code == 400


async def test_invalid_code_is_rejected(client: httpx.AsyncClient) -> None:
    state = await start_login(client)
    resp = await client.get(
        f"{API}/auth/github/callback", params={"code": "bad-code", "state": state}
    )
    assert resp.status_code == 401


async def test_repeated_login_reuses_the_same_account(client: httpx.AsyncClient) -> None:
    ids = []
    for _ in range(2):
        state = await start_login(client)
        tokens = (
            await client.get(
                f"{API}/auth/github/callback", params={"code": "good-code", "state": state}
            )
        ).json()
        ids.append((await client.get(f"{API}/users/me", headers=bearer(tokens))).json()["id"])
    assert ids[0] == ids[1]


async def test_existing_password_account_is_linked_by_verified_email(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    existing = await make_user("octocat@example.com", is_author=True)
    state = await start_login(client)
    tokens = (
        await client.get(
            f"{API}/auth/github/callback", params={"code": "good-code", "state": state}
        )
    ).json()
    me = (await client.get(f"{API}/users/me", headers=bearer(tokens))).json()
    assert me["id"] == existing.id
    assert me["is_author"] is True


async def test_unverified_email_is_rejected(
    client: httpx.AsyncClient, fake_github: FakeGitHub
) -> None:
    fake_github.emails = [{"email": "x@example.com", "primary": True, "verified": False}]
    state = await start_login(client)
    resp = await client.get(
        f"{API}/auth/github/callback", params={"code": "good-code", "state": state}
    )
    assert resp.status_code == 401
    assert "verified" in resp.json()["error"]["message"]
