import httpx

from tests.conftest import PASSWORD, Login, MakeUser, bearer

API = "/api/v1"


async def test_register_creates_user_without_exposing_password(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        f"{API}/auth/register",
        json={"name": "  Grigory ", "email": "Grigory@Example.com", "password": "Secret123"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "grigory@example.com"
    assert body["name"] == "Grigory"
    assert body["is_author"] is False
    assert "password" not in body and "hashed_password" not in body


async def test_register_duplicate_email_is_case_insensitive(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("taken@example.com")
    resp = await client.post(
        f"{API}/auth/register",
        json={"name": "X", "email": "TAKEN@example.com", "password": "Secret123"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


async def test_register_rejects_weak_password(client: httpx.AsyncClient) -> None:
    for password in ("short1", "onlyletters", "1234567890"):
        resp = await client.post(
            f"{API}/auth/register",
            json={"name": "X", "email": "x@example.com", "password": password},
        )
        assert resp.status_code == 422, password


async def test_login_returns_working_token_pair(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    tokens = await login("ME@example.com")
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] > 0
    me = await client.get(f"{API}/users/me", headers=bearer(tokens))
    assert me.status_code == 200
    assert me.json()["email"] == "me@example.com"


async def test_login_errors_do_not_reveal_whether_email_exists(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("me@example.com")
    wrong_password = await client.post(
        f"{API}/auth/login", json={"email": "me@example.com", "password": "Wrong1234"}
    )
    unknown_email = await client.post(
        f"{API}/auth/login", json={"email": "nobody@example.com", "password": "Wrong1234"}
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_oauth_only_account_cannot_login_with_password(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("oauth@example.com", password=None)
    resp = await client.post(
        f"{API}/auth/login", json={"email": "oauth@example.com", "password": "Anything123"}
    )
    assert resp.status_code == 401


async def test_disabled_user_cannot_login(client: httpx.AsyncClient, make_user: MakeUser) -> None:
    await make_user("off@example.com", is_active=False)
    resp = await client.post(
        f"{API}/auth/login", json={"email": "off@example.com", "password": PASSWORD}
    )
    assert resp.status_code == 403


async def test_login_is_rate_limited_after_failed_attempts(
    client: httpx.AsyncClient, make_user: MakeUser
) -> None:
    await make_user("me@example.com")
    bad = {"email": "me@example.com", "password": "Wrong1234"}
    for _ in range(3):  # login_rate_limit=3 in test settings
        assert (await client.post(f"{API}/auth/login", json=bad)).status_code == 401

    blocked = await client.post(
        f"{API}/auth/login", json={"email": "me@example.com", "password": PASSWORD}
    )
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


async def test_successful_login_resets_failed_attempts(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    bad = {"email": "me@example.com", "password": "Wrong1234"}
    for _ in range(2):
        await client.post(f"{API}/auth/login", json=bad)
    await login("me@example.com")
    for _ in range(2):
        assert (await client.post(f"{API}/auth/login", json=bad)).status_code == 401


async def test_protected_endpoint_requires_valid_token(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{API}/users/me")).status_code == 401
    resp = await client.get(f"{API}/users/me", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


async def test_refresh_rotates_tokens(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    first = await login("me@example.com")

    resp = await client.post(f"{API}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert resp.status_code == 200
    second = resp.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await client.get(f"{API}/users/me", headers=bearer(second))).status_code == 200


async def test_reusing_rotated_refresh_token_revokes_all_sessions(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    stolen = (await login("me@example.com"))["refresh_token"]
    legit = (await client.post(f"{API}/auth/refresh", json={"refresh_token": stolen})).json()[
        "refresh_token"
    ]

    reuse = await client.post(f"{API}/auth/refresh", json={"refresh_token": stolen})
    assert reuse.status_code == 401
    assert "reuse" in reuse.json()["error"]["message"]

    # The attacker's replay also kills the legitimate session.
    after = await client.post(f"{API}/auth/refresh", json={"refresh_token": legit})
    assert after.status_code == 401


async def test_unknown_refresh_token_is_rejected(client: httpx.AsyncClient) -> None:
    resp = await client.post(f"{API}/auth/refresh", json={"refresh_token": "nope"})
    assert resp.status_code == 401


async def test_logout_revokes_refresh_token_and_is_idempotent(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    tokens = await login("me@example.com")
    body = {"refresh_token": tokens["refresh_token"]}
    assert (await client.post(f"{API}/auth/logout", json=body)).status_code == 204
    assert (await client.post(f"{API}/auth/logout", json=body)).status_code == 204
    assert (await client.post(f"{API}/auth/refresh", json=body)).status_code == 401


async def test_sessions_can_be_listed_and_revoked(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    phone = await login("me@example.com")
    laptop = await login("me@example.com")

    sessions = (await client.get(f"{API}/auth/sessions", headers=bearer(laptop))).json()
    assert len(sessions) == 2

    oldest = min(s["id"] for s in sessions)
    resp = await client.delete(f"{API}/auth/sessions/{oldest}", headers=bearer(laptop))
    assert resp.status_code == 204
    revoked = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": phone["refresh_token"]}
    )
    assert revoked.status_code == 401
    # A token that was revoked on purpose is just invalid; the other session survives.
    assert "reuse" not in revoked.json()["error"]["message"]
    still_ok = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": laptop["refresh_token"]}
    )
    assert still_ok.status_code == 200


async def test_cannot_revoke_someone_elses_session(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("a@example.com")
    await make_user("b@example.com")
    a = await login("a@example.com")
    b = await login("b@example.com")
    b_session = (await client.get(f"{API}/auth/sessions", headers=bearer(b))).json()[0]["id"]

    resp = await client.delete(f"{API}/auth/sessions/{b_session}", headers=bearer(a))
    assert resp.status_code == 404


async def test_session_limit_evicts_oldest_session(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    logins = [await login("me@example.com") for _ in range(4)]  # max_sessions_per_user=3

    sessions = (await client.get(f"{API}/auth/sessions", headers=bearer(logins[-1]))).json()
    assert len(sessions) == 3
    evicted = await client.post(
        f"{API}/auth/refresh", json={"refresh_token": logins[0]["refresh_token"]}
    )
    assert evicted.status_code == 401


async def test_logout_all_revokes_every_session(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    await make_user("me@example.com")
    first = await login("me@example.com")
    second = await login("me@example.com")
    assert (await client.post(f"{API}/auth/logout-all", headers=bearer(second))).status_code == 204
    for tokens in (first, second):
        resp = await client.post(
            f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert resp.status_code == 401
