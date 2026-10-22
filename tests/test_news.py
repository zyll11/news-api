import fakeredis
import httpx

API = "/api/v1"
ARTICLE = {"title": "Hello", "content": {"body": "First post"}}


async def create_news(client: httpx.AsyncClient, headers: dict[str, str], **overrides) -> dict:
    resp = await client.post(f"{API}/news", json={**ARTICLE, **overrides}, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_author_can_publish_news(
    client: httpx.AsyncClient, author_headers: dict[str, str]
) -> None:
    news = await create_news(client, author_headers, cover_image="https://img.example.com/a.png")
    assert news["title"] == "Hello"
    assert news["author"]["name"] == "Author"
    assert "email" not in news["author"]
    assert news["cover_image"] == "https://img.example.com/a.png"


async def test_reader_and_anonymous_cannot_publish(
    client: httpx.AsyncClient, reader_headers: dict[str, str]
) -> None:
    assert (await client.post(f"{API}/news", json=ARTICLE)).status_code == 401
    resp = await client.post(f"{API}/news", json=ARTICLE, headers=reader_headers)
    assert resp.status_code == 403


async def test_news_validation(client: httpx.AsyncClient, author_headers: dict[str, str]) -> None:
    for payload in (
        {"title": "   ", "content": {"body": "x"}},
        {"title": "ok", "content": {}},
        {"title": "x" * 256, "content": {"body": "x"}},
        {"title": "ok", "content": {"body": "x"}, "cover_image": "not-a-url"},
    ):
        resp = await client.post(f"{API}/news", json=payload, headers=author_headers)
        assert resp.status_code == 422, payload


async def test_list_is_public_paginated_and_newest_first(
    client: httpx.AsyncClient, author_headers: dict[str, str]
) -> None:
    for i in range(3):
        await create_news(client, author_headers, title=f"News {i}")

    page = (await client.get(f"{API}/news", params={"limit": 2})).json()
    assert page["total"] == 3
    assert [n["title"] for n in page["items"]] == ["News 2", "News 1"]

    rest = (await client.get(f"{API}/news", params={"offset": 2, "limit": 2})).json()
    assert [n["title"] for n in rest["items"]] == ["News 0"]


async def test_page_size_is_capped(client: httpx.AsyncClient) -> None:
    assert (await client.get(f"{API}/news", params={"limit": 1000})).status_code == 422


async def test_get_missing_news_returns_404(client: httpx.AsyncClient) -> None:
    resp = await client.get(f"{API}/news/999")
    assert resp.status_code == 404
    assert resp.json() == {"error": {"code": "not_found", "message": "News not found"}}


async def test_owner_can_partially_update(
    client: httpx.AsyncClient, author_headers: dict[str, str]
) -> None:
    news = await create_news(client, author_headers)
    resp = await client.patch(
        f"{API}/news/{news['id']}", json={"title": "Updated"}, headers=author_headers
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "Updated"
    assert resp.json()["content"] == ARTICLE["content"]


async def test_update_rejects_empty_or_null_fields(
    client: httpx.AsyncClient, author_headers: dict[str, str]
) -> None:
    news = await create_news(client, author_headers)
    for payload in ({}, {"title": None}, {"content": None}):
        resp = await client.patch(f"{API}/news/{news['id']}", json=payload, headers=author_headers)
        assert resp.status_code == 422, payload


async def test_cover_image_can_be_removed(
    client: httpx.AsyncClient, author_headers: dict[str, str]
) -> None:
    news = await create_news(client, author_headers, cover_image="https://img.example.com/a.png")
    resp = await client.patch(
        f"{API}/news/{news['id']}", json={"cover_image": None}, headers=author_headers
    )
    assert resp.json()["cover_image"] is None


async def test_other_author_cannot_modify(
    client: httpx.AsyncClient,
    author_headers: dict[str, str],
    other_author_headers: dict[str, str],
) -> None:
    news = await create_news(client, author_headers)
    url = f"{API}/news/{news['id']}"
    assert (
        await client.patch(url, json={"title": "Hijacked"}, headers=other_author_headers)
    ).status_code == 403
    assert (await client.delete(url, headers=other_author_headers)).status_code == 403


async def test_admin_can_modify_and_delete_any_news(
    client: httpx.AsyncClient, author_headers: dict[str, str], admin_headers: dict[str, str]
) -> None:
    news = await create_news(client, author_headers)
    url = f"{API}/news/{news['id']}"
    assert (
        await client.patch(url, json={"title": "Moderated"}, headers=admin_headers)
    ).status_code == 200
    assert (await client.delete(url, headers=admin_headers)).status_code == 204
    assert (await client.get(url)).status_code == 404


async def test_deleting_news_deletes_its_comments(
    client: httpx.AsyncClient, author_headers: dict[str, str], reader_headers: dict[str, str]
) -> None:
    news = await create_news(client, author_headers)
    comment = (
        await client.post(
            f"{API}/news/{news['id']}/comments", json={"text": "Nice"}, headers=reader_headers
        )
    ).json()
    await client.delete(f"{API}/news/{news['id']}", headers=author_headers)

    resp = await client.patch(
        f"{API}/comments/{comment['id']}", json={"text": "Edit"}, headers=reader_headers
    )
    assert resp.status_code == 404


async def test_news_is_cached_and_cache_is_invalidated_on_update(
    client: httpx.AsyncClient,
    author_headers: dict[str, str],
    redis: fakeredis.FakeAsyncRedis,
) -> None:
    news = await create_news(client, author_headers)
    url = f"{API}/news/{news['id']}"

    await client.get(url)
    await client.get(f"{API}/news")
    assert await redis.exists(f"news:item:{news['id']}")
    page_keys = [k for k in await redis.keys("news:list:v*") if k != "news:list:version"]
    assert page_keys

    await client.patch(url, json={"title": "Fresh"}, headers=author_headers)
    assert not await redis.exists(f"news:item:{news['id']}")
    assert (await client.get(url)).json()["title"] == "Fresh"
    assert (await client.get(f"{API}/news")).json()["items"][0]["title"] == "Fresh"


async def test_api_keeps_working_when_redis_is_down(
    client: httpx.AsyncClient,
    author_headers: dict[str, str],
    redis_server: fakeredis.FakeServer,
) -> None:
    news = await create_news(client, author_headers)
    redis_server.connected = False  # every Redis command now raises ConnectionError
    resp = await client.get(f"{API}/news/{news['id']}")
    assert resp.status_code == 200
    assert (await client.get(f"{API}/news")).status_code == 200
    updated = await client.patch(
        f"{API}/news/{news['id']}", json={"title": "Still works"}, headers=author_headers
    )
    assert updated.status_code == 200
