import httpx

API = "/api/v1"


async def make_news(client: httpx.AsyncClient, headers: dict[str, str]) -> int:
    resp = await client.post(
        f"{API}/news", json={"title": "T", "content": {"body": "B"}}, headers=headers
    )
    return int(resp.json()["id"])


async def test_any_user_can_comment_and_list_is_public(
    client: httpx.AsyncClient, author_headers: dict[str, str], reader_headers: dict[str, str]
) -> None:
    news_id = await make_news(client, author_headers)
    resp = await client.post(
        f"{API}/news/{news_id}/comments", json={"text": "  Great!  "}, headers=reader_headers
    )
    assert resp.status_code == 201
    assert resp.json()["text"] == "Great!"
    assert resp.json()["author"]["name"] == "Reader"

    page = (await client.get(f"{API}/news/{news_id}/comments")).json()
    assert page["total"] == 1
    assert page["items"][0]["text"] == "Great!"


async def test_anonymous_cannot_comment(
    client: httpx.AsyncClient, author_headers: dict[str, str]
) -> None:
    news_id = await make_news(client, author_headers)
    resp = await client.post(f"{API}/news/{news_id}/comments", json={"text": "Hi"})
    assert resp.status_code == 401


async def test_comment_on_missing_news_returns_404(
    client: httpx.AsyncClient, reader_headers: dict[str, str]
) -> None:
    resp = await client.post(f"{API}/news/404/comments", json={"text": "x"}, headers=reader_headers)
    assert resp.status_code == 404
    assert (await client.get(f"{API}/news/404/comments")).status_code == 404


async def test_empty_comment_is_rejected(
    client: httpx.AsyncClient, author_headers: dict[str, str], reader_headers: dict[str, str]
) -> None:
    news_id = await make_news(client, author_headers)
    resp = await client.post(
        f"{API}/news/{news_id}/comments", json={"text": "   "}, headers=reader_headers
    )
    assert resp.status_code == 422


async def test_only_owner_or_admin_can_modify_comment(
    client: httpx.AsyncClient,
    author_headers: dict[str, str],
    reader_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    news_id = await make_news(client, author_headers)
    comment = (
        await client.post(
            f"{API}/news/{news_id}/comments", json={"text": "Mine"}, headers=reader_headers
        )
    ).json()
    url = f"{API}/comments/{comment['id']}"

    # The news author does not own the reader's comment.
    assert (await client.patch(url, json={"text": "X"}, headers=author_headers)).status_code == 403
    assert (await client.delete(url, headers=author_headers)).status_code == 403

    edited = await client.patch(url, json={"text": "Edited"}, headers=reader_headers)
    assert edited.status_code == 200
    assert edited.json()["text"] == "Edited"

    assert (await client.delete(url, headers=admin_headers)).status_code == 204
    assert (await client.get(f"{API}/news/{news_id}/comments")).json()["total"] == 0
