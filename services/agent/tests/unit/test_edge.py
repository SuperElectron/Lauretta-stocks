"""Only the gateway reaches the api: a request without its secret header is refused."""

import contextlib

import httpx
import pytest

from src.api.app import create_app
from tests.unit.openai.conftest import broker  # noqa: F401 (fixture)
from tests.utils import settings

SECRET = "s3cret-from-the-gateway"


@contextlib.asynccontextmanager
async def api(broker, headers):  # noqa: F811
    app = create_app(with_lifespan=False)
    app.state.settings = settings(API_GATEWAY_SECRET=SECRET)
    app.state.broker, app.state.pool = broker, None
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://api", headers=headers
    ) as http:
        yield http


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Lauretta-User": "mat"},
        {"X-Lauretta-User": "mat", "X-Lauretta-Gateway": "guess"},
    ],
)
async def test_a_forged_user_without_the_gateway_secret_is_refused(broker, headers):  # noqa: F811
    async with api(broker, headers) as http:
        for path in ("/v1/holdings", "/v1/models", "/mcp/", "/mcp"):
            response = await http.get(path)
            assert response.status_code == 401, path
            assert response.json()["detail"]["code"] == "NOT_FROM_GATEWAY"


async def test_the_gateway_secret_lets_the_request_through(broker):  # noqa: F811
    headers = {"X-Lauretta-User": "mat", "X-Lauretta-Gateway": SECRET}
    async with api(broker, headers) as http:
        response = await http.get("/v1/models")
    assert response.status_code == 200


async def test_mcp_without_a_slash_is_served_not_redirected(broker):  # noqa: F811
    headers = {"X-Lauretta-Gateway": SECRET}
    async with api(broker, headers) as http:
        response = await http.post("/mcp", json={})
    assert response.status_code != 307
