"""The MCP server for Goose and other MCP clients: streamable HTTP at `/mcp/`, inside the API.

The gateway authenticates the caller and names the user in `X-Lauretta-User`, exactly as for
`/v1/*`; a tool reads that header from the HTTP request it arrived on and acts for that user
alone. Stateless: every request stands on its own, so nothing is kept between calls.
"""

from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.datastructures import State

from src.api.deps import USER_HEADER
from src.api.mcpserver.desk import Desk, DeskError
from src.prompts import errors as wording

mcp = FastMCP(
    "lauretta",
    stateless_http=True,
    json_response=False,
    streamable_http_path="/",
    # Only the gateway reaches the API (compose networks), and it sets the Host it forwards; the
    # gateway's own key check stands in for the DNS-rebinding guard meant for local servers.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)
# The API's state (broker, pool, settings), bound by the API's lifespan.
bound = State()


def desk_for(ctx: Context) -> Desk:
    """The desk for the user the gateway named on this request; a tool error otherwise."""
    request = ctx.request_context.request
    named = request.headers.getlist(USER_HEADER) if request is not None else []
    settings = bound.settings
    if len(named) != 1 or named[0] not in settings.allowed_users():
        raise DeskError(wording.UNKNOWN_USER)
    return Desk(bound.broker, bound.pool, settings, named[0])


def _progress(ctx: Context):
    steps = 0

    async def report(line: str) -> None:
        nonlocal steps
        steps += 1
        await ctx.report_progress(steps, message=line)

    return report


@mcp.tool()
async def ask_assistant(message: str, ctx: Context, thread_id: str = "mcp") -> dict[str, Any]:
    """Send a message to the Director, the investor's research assistant, and wait for the
    reply. Conversations continue per thread_id. It never places trades."""
    desk = desk_for(ctx)
    job_id = await desk.start(kind="chat", message=message, thread_id=thread_id)
    return await desk.follow(job_id, _progress(ctx))


@mcp.tool()
async def research_stock(ticker: str, ctx: Context) -> dict[str, Any]:
    """Run the research team on a ticker (analyst draft, checker review, strategist suggestion)
    and wait for the saved thesis. Takes minutes; progress is reported as it goes."""
    desk = desk_for(ctx)
    job_id = await desk.start(kind="research", ticker=ticker)
    return await desk.follow(job_id, _progress(ctx))


@mcp.tool()
async def start_research(ticker: str, ctx: Context) -> dict[str, str]:
    """Queue a research run on a ticker without waiting; poll it with get_job."""
    return {"job_id": await desk_for(ctx).start(kind="research", ticker=ticker)}


@mcp.tool()
async def get_job(job_id: str, ctx: Context) -> dict[str, Any]:
    """A queued job's status, with its result or error once it has finished."""
    return await desk_for(ctx).job(job_id)


@mcp.tool()
async def get_thesis(ticker: str, ctx: Context) -> dict[str, Any]:
    """The latest saved research thesis on a ticker."""
    return await desk_for(ctx).thesis(ticker)


@mcp.tool()
async def holdings(ctx: Context) -> list[dict[str, Any]]:
    """The investor's recorded holdings."""
    return await desk_for(ctx).holdings()
