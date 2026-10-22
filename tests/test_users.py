import httpx

from tests.conftest import Login, MakeUser, bearer

API = "/api/v1"


async def test_user_can_update_own_profile(
    client: httpx.AsyncClient, reader_headers: dict[str, str]
) -> None:
    resp = await client.patch(
        f"{API}/users/me",
        json={"name": "New Name", "avatar": "https://img.example.com/me.png"},
        headers=reader_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"
    assert resp.json()["avatar"] == "https://img.example.com/me.png"


async def test_profile_update_cannot_grant_roles(
    client: httpx.AsyncClient, reader_headers: dict[str, str]
) -> None:
    resp = await client.patch(
        f"{API}/users/me",
        json={"name": "X", "is_admin": True, "is_author": True},
        headers=reader_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_admin"] is False
    assert resp.json()["is_author"] is False


async def test_users_can_only_view_themselves(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login
) -> None:
    alice = await make_user("alice@example.com")
    bob = await make_user("bob@example.com")
    headers = bearer(await login("alice@example.com"))
    assert (await client.get(f"{API}/users/{alice.id}", headers=headers)).status_code == 200
    assert (await client.get(f"{API}/users/{bob.id}", headers=headers)).status_code == 403


async def test_listing_users_requires_admin(
    client: httpx.AsyncClient, reader_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    assert (await client.get(f"{API}/users", headers=reader_headers)).status_code == 403
    page = (await client.get(f"{API}/users", headers=admin_headers)).json()
    assert page["total"] == 2


async def test_admin_can_grant_author_role(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login, admin_headers: dict[str, str]
) -> None:
    user = await make_user("writer@example.com")
    headers = bearer(await login("writer@example.com"))
    article = {"title": "T", "content": {"body": "B"}}
    assert (await client.post(f"{API}/news", json=article, headers=headers)).status_code == 403

    resp = await client.patch(
        f"{API}/users/{user.id}/roles", json={"is_author": True}, headers=admin_headers
    )
    assert resp.status_code == 200
    assert (await client.post(f"{API}/news", json=article, headers=headers)).status_code == 201


async def test_non_admin_cannot_change_roles(
    client: httpx.AsyncClient, make_user: MakeUser, reader_headers: dict[str, str]
) -> None:
    other = await make_user("other@example.com")
    resp = await client.patch(
        f"{API}/users/{other.id}/roles", json={"is_author": True}, headers=reader_headers
    )
    assert resp.status_code == 403


async def test_disabled_user_token_stops_working(
    client: httpx.AsyncClient, make_user: MakeUser, login: Login, database
) -> None:
    from app.models import User

    user = await make_user("soon-off@example.com")
    headers = bearer(await login("soon-off@example.com"))
    async with database.sessionmaker() as session:
        db_user = await session.get(User, user.id)
        db_user.is_active = False
        await session.commit()
    assert (await client.get(f"{API}/users/me", headers=headers)).status_code == 401
