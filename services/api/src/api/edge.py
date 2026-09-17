"""What every request must show before any route runs: that the gateway sent it.

Compose keeps api on networks with the gateway, the database, the broker and the speech service.
Networks alone are not trusted: the gateway adds `X-Lauretta-Gateway` with a secret only it and
api hold, and anything without it is refused, so no other container can forge a user header.
`/healthz` stays open for the container's own healthcheck. Also, `/mcp` is answered as `/mcp/`
here rather than redirected, because behind the gateway a redirect would name the wrong scheme.
"""

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

from src.prompts import errors as wording

GATEWAY_HEADER = b"x-lauretta-gateway"
OPEN_PATHS = frozenset({"/healthz"})


class GatewayOnly:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        if scope["path"] == "/mcp":
            scope = {**scope, "path": "/mcp/", "raw_path": b"/mcp/"}
        settings = getattr(scope["app"].state, "settings", None) if "app" in scope else None
        secret = getattr(settings, "API_GATEWAY_SECRET", None)
        if secret and scope["path"] not in OPEN_PATHS and not _sent_by_gateway(scope, secret):
            await _refuse(scope, send)
            return
        await self.app(scope, receive, send)


def _sent_by_gateway(scope: Scope, secret: str) -> bool:
    found = [value for name, value in scope["headers"] if name == GATEWAY_HEADER]
    return len(found) == 1 and hmac.compare_digest(found[0], secret.encode())


async def _refuse(scope: Scope, send: Send) -> None:
    if scope["type"] == "websocket":
        await send({"type": "websocket.close", "code": 1008})
        return
    body = json.dumps({"detail": {"code": "NOT_FROM_GATEWAY", "message": wording.NOT_FROM_GATEWAY}})
    headers = [(b"content-type", b"application/json")]
    await send({"type": "http.response.start", "status": 401, "headers": headers})
    await send({"type": "http.response.body", "body": body.encode()})
