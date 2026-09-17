"""Reads annual figures out of an EDGAR companyfacts document. Pure functions, no I/O."""

from datetime import date
from typing import Any

# A fiscal year reported as a duration is roughly 52 or 53 weeks.
_YEAR_DAYS = range(350, 380)
_ANNUAL_FORMS = frozenset({"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"})


def annual_series(taxonomies: dict[str, Any], tags: tuple[str, ...], years: int) -> dict[str, Any]:
    """The line item's last `years` fiscal years, from whichever tag reports the latest year.

    Companies move between tags over time, so the tag with the most recent annual figure
    wins. Returns `found: false` when no tag has an annual figure.
    """
    best: tuple[str, str, list[dict[str, Any]]] | None = None
    for tag in tags:
        taxonomy, name = tag.split(":")
        concept = taxonomies.get(taxonomy, {}).get(name)
        if concept is None:
            continue
        for unit, facts in concept["units"].items():
            points = annual_points(facts)
            if points and (best is None or points[0]["period_end"] > best[2][0]["period_end"]):
                best = (tag, unit, points)
    if best is None:
        return {"found": False}
    tag, unit, points = best
    return {"found": True, "tag": tag, "unit": unit, "years": points[:years]}


def annual_points(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One figure per fiscal year end, newest first, as the latest annual filing stated it."""
    by_end: dict[str, dict[str, Any]] = {}
    for fact in facts:
        if fact.get("form") not in _ANNUAL_FORMS or not _is_annual(fact):
            continue
        current = by_end.get(fact["end"])
        if current is None or fact["filed"] > current["filed"]:
            by_end[fact["end"]] = fact
    return [
        {"period_end": end, "value": fact["val"], "filed": fact["filed"]}
        for end, fact in sorted(by_end.items(), reverse=True)
    ]


def _is_annual(fact: dict[str, Any]) -> bool:
    """A balance-sheet figure (an instant) at year end, or a flow covering a whole year."""
    if "start" not in fact:
        return fact.get("fp") == "FY"
    days = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
    return days in _YEAR_DAYS


# A line item whose newest year ends this long before revenue's is no longer reported.
STALE_DAYS = 450


def mark_stale(items: dict[str, dict[str, Any]], anchor: str = "revenue") -> dict[str, Any]:
    """Flags each series that stopped long before the anchor's latest year, so it is not
    read as current."""
    if not items.get(anchor, {}).get("found"):
        return items
    latest = date.fromisoformat(items[anchor]["years"][0]["period_end"])
    for series in items.values():
        if series.get("found"):
            end = date.fromisoformat(series["years"][0]["period_end"])
            series["stale"] = (latest - end).days > STALE_DAYS
    return items
