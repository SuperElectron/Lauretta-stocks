"""Read-only routes on what the worker saved, and the health check."""

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger

from src.api.deps import BrokerDep, PoolDep, SettingsDep
from src.db.pool import rows
from src.db.queries import holdings, theses
from src.prompts import errors as wording

router = APIRouter()


@router.get("/v1/theses/{ticker}")
async def latest_thesis(ticker: str, pool: PoolDep, settings: SettingsDep) -> dict[str, Any]:
    saved = await theses.latest(pool, settings.USER_ID, ticker)
    if saved is None:
        raise HTTPException(
            404,
            detail={
                "code": "THESIS_NOT_FOUND",
                "message": wording.NO_RESEARCH.format(ticker=ticker),
            },
        )
    return saved


@router.get("/v1/holdings")
async def all_holdings(pool: PoolDep, settings: SettingsDep) -> dict[str, Any]:
    return {"holdings": await holdings.all_of(pool, settings.USER_ID)}


@router.get("/healthz")
async def healthz(pool: PoolDep, broker: BrokerDep) -> JSONResponse:
    """200 when both the database and the broker answer, else 503 naming which did not."""
    checks: dict[str, str] = {}
    for name, check in (("db", lambda: rows(pool, "SELECT 1")), ("broker", broker.ping)):
        try:
            await check()
            checks[name] = "ok"
        except Exception as exc:
            logger.bind(check=name, error=type(exc).__name__).error("healthz.failed")
            checks[name] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(checks, status_code=200 if healthy else 503)
