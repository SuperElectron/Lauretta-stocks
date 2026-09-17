"""The desk's names: defaults, renames kept as identity facts with history, and where they show."""

from contextlib import asynccontextmanager
from typing import Any

import pytest

from src.db.queries import facts
from src.graph.ctx import Ctx
from src.graph.pipeline import Team, build_pipeline
from src.persona.layers import build_persona, desk_names, render_persona
from src.report import render_report
from src.tools.persona import build_set_identity
from tests.utils import ADVICE, REVIEW, STORY, Recorder, run_as


class FactsTable:
    """Just enough of the facts table for `facts.set_keyed`: find active, supersede, insert."""

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []
        # The user each transaction was scoped to, and the persona locks taken.
        self.scopes: list[str] = []
        self.locks: list[str] = []

    async def execute(self, sql: str, params: tuple) -> "FactsTable":
        if "set_config('app.user_id'" in sql:
            self.scopes.append(params[0])
        elif "pg_advisory_xact_lock" in sql:
            self.locks.append(params[0])
        elif sql.lstrip().startswith("SELECT"):
            user_id, subject, key = params
            wanted = (user_id, subject, key, "active")
            self.found = [
                r
                for r in self.rows
                if (r["user_id"], r["subject"], r["key"], r["status"]) == wanted
            ]
        elif sql.lstrip().startswith("UPDATE"):
            self.rows[params[0]]["status"] = "superseded"
        else:
            user_id, subject, kind, key, content, value, _vector, source, supersedes = params
            self.rows.append({
                "id": len(self.rows), "user_id": user_id, "subject": subject, "kind": kind,
                "key": key, "content": content, "value": value.obj, "source": source,
                "supersedes": supersedes, "status": "active", "created": "2026-09-16",
            })  # fmt: skip
            self.found = [{"id": str(len(self.rows) - 1)}]
        return self

    description = True

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.found

    @asynccontextmanager
    async def connection(self):
        yield self

    @asynccontextmanager
    async def cursor(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        yield self

    def active(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["status"] == "active"]


class Embedder:
    async def embed(self, _text: str) -> list[float]:
        return [0.0] * 384


def test_defaults_render_in_the_identity_block():
    block = render_persona(build_persona([]))
    for line in ("bot_name: the Director", "analyst_name: Andy", "checker_name: Charlie",
                 "strategist_name: Sammy"):  # fmt: skip
        assert line in block


async def test_set_identity_renames_agents_and_keeps_the_old_names():
    table = FactsTable()
    set_identity = build_set_identity(table, Embedder())

    await run_as("friend", set_identity, {"analyst_name": "Sarah", "checker_name": "Ivy"})
    await run_as("friend", set_identity, {"strategist_name": "Rex", "analyst_name": "Tom"})

    names = desk_names(build_persona(table.active()))
    assert names == {
        "bot_name": "the Director", "analyst_name": "Tom", "checker_name": "Ivy",
        "strategist_name": "Rex",
    }  # fmt: skip
    old, new = [r for r in table.rows if r["key"] == "analyst_name"]
    assert old["status"] == "superseded" and new["supersedes"] == old["id"]
    assert new["content"] == "The investor calls the Analyst Tom." and new["kind"] == "identity"
    assert "analyst_name: Tom" in render_persona(build_persona(table.active()))


async def test_the_same_name_twice_writes_nothing():
    table = FactsTable()
    await facts.set_keyed(table, Embedder(), "friend", "checker_name", "Ivy", "chat")
    assert (await facts.set_keyed(table, Embedder(), "friend", "checker_name", "Ivy", "chat"))[
        "changed"
    ] is False
    assert len(table.rows) == 1


@pytest.mark.usefixtures("no_database")
async def test_each_role_is_told_its_name_and_the_report_uses_them():
    analyst, checker, advisor = Recorder(STORY), Recorder(REVIEW), Recorder(ADVICE)
    pipeline = build_pipeline(None, Team(analyst, checker, advisor), max_revisions=1)
    final = await pipeline.ainvoke({"ticker": "MSFT"}, context=Ctx(user_id="friend"))

    assert analyst.prompts[0].startswith("You are Sarah, the Analyst")
    assert checker.prompts[0].startswith("You are Charlie, the Checker")
    assert "Sarah (the Analyst)" in checker.prompts[0]
    assert advisor.prompts[0].startswith("You are Sammy, the Strategist")
    report = render_report(final)
    for heading in ("## Story (Sarah, Analyst)", "## Checker review (Charlie)",
                    "## Strategist (Sammy)", "Checker (Charlie): **approve**"):  # fmt: skip
        assert heading in report
    assert render_report({k: v for k, v in final.items() if k != "names"}).count("Andy") == 1
