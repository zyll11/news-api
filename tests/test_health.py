import fakeredis
import httpx


async def test_liveness(client: httpx.AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"]


async def test_readiness_reports_dependencies(
    client: httpx.AsyncClient, redis_server: fakeredis.FakeServer
) -> None:
    ok = await client.get("/health/ready")
    assert ok.status_code == 200
    assert ok.json()["checks"] == {"database": "ok", "redis": "ok"}

    redis_server.connected = False
    degraded = await client.get("/health/ready")
    assert degraded.status_code == 503
    assert degraded.json()["checks"]["redis"] == "unavailable"


async def test_openapi_schema_is_generated(client: httpx.AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/api/v1/news" in resp.json()["paths"]
