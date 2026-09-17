from typing import Any

import pytest

from src.graph import pipeline as pipeline_module
from src.graph.context import Known
from src.memory.topics import CORE_TOPICS
from src.persona.layers import build_persona, desk_names

DEFAULT_NAMES = desk_names(build_persona([]))


@pytest.fixture
def no_database(monkeypatch):
    saved: dict[str, Any] = {}

    # Every core topic known but risk tolerance; the Analyst renamed; money counted in GBP.
    remembered = [
        {"id": topic, "topic": topic, "content": topic, "created": "2026-09-16"}
        for topic in CORE_TOPICS
        if topic != "risk_tolerance"
    ]
    persona = build_persona([
        {"kind": "identity", "key": "analyst_name", "value": "Sarah", "content": "", "created": ""},
        {"kind": "profile", "key": "currency", "value": "GBP", "content": "", "created": ""},
    ])  # fmt: skip

    async def load_known(_pool, _user_id):
        return Known(persona=persona, remembered=remembered, positions=[])

    async def save(_pool, _user_id, ticker, story, review, advice, revisions):
        saved.update(ticker=ticker, story=story, review=review, advice=advice, revisions=revisions)
        return "thesis-1"

    monkeypatch.setattr(pipeline_module, "load_known", load_known)
    monkeypatch.setattr(pipeline_module.theses, "save", save)
    return saved
