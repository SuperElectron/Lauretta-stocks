"""The optional `callback_url`: the job's outcome is POSTed once, never retried."""

import httpx
from loguru import logger


async def deliver(url: str, body: dict, timeout_s: float) -> str | None:
    """Posts `body`; returns None when delivered, else a short reason (no response body)."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        reason = f"HTTP {exc.response.status_code}"
    except httpx.HTTPError as exc:
        reason = type(exc).__name__
    else:
        return None
    logger.bind(job_id=body.get("job_id"), reason=reason).error("callback.failed")
    return reason
