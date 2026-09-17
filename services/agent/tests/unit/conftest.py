from typing import Any

import pytest

from src.graph import pipeline as pipeline_module


@pytest.fixture
def no_database(monkeypatch):
    saved: dict[str, Any] = {}

    async def investor_blocks(_pool, _user_id):
        return "<investor>\nnothing yet\n</investor>", ["risk_tolerance"]

    async def advisor_user_block(_pool, _user_id):
        return "<user>\ncurrency: GBP\n</user>"

    async def save(_pool, _user_id, ticker, story, review, advice, revisions):
        saved.update(ticker=ticker, story=story, review=review, advice=advice, revisions=revisions)
        return "thesis-1"

    monkeypatch.setattr(pipeline_module, "investor_blocks", investor_blocks)
    monkeypatch.setattr(pipeline_module, "advisor_user_block", advisor_user_block)
    monkeypatch.setattr(pipeline_module.theses, "save", save)
    return saved
