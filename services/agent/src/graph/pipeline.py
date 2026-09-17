"""The research desk: the Analyst drafts, the Checker checks (and may send it back), the
Strategist suggests. Each agent goes by the investor's name for it, loaded once per run.

Built once for everyone; a run acts for the user in its context (`Ctx`), whose profile and
holdings it reads, whose thesis it saves, and whose context each role (and its tools) runs with."""

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from psycopg_pool import AsyncConnectionPool

from src.db.queries import theses
from src.graph import emit
from src.graph.context import advisor_user_block, investor_blocks, load_known
from src.graph.ctx import Ctx, user_of
from src.graph.render import render_advisor_prompt, render_analyst_prompt, render_checker_prompt
from src.graph.role import Role
from src.graph.setup import missing_core, setup_of
from src.graph.state import PipelineState
from src.persona.layers import desk_names
from src.prompts import analyst as analyst_text
from src.prompts import checker as checker_text
from src.prompts import progress
from src.prompts import strategist as strategist_text


@dataclass(frozen=True)
class Team:
    analyst: Role
    checker: Role
    advisor: Role


def needs_revision(state: PipelineState, max_revisions: int) -> bool:
    """The checker asked for changes and the analyst still has a redraft left."""
    review = state.get("review") or {}
    return review.get("verdict") == "revise" and state.get("revisions", 0) < max_revisions


def build_pipeline(pool: AsyncConnectionPool, team: Team, max_revisions: int) -> CompiledStateGraph:
    async def load_context(_state: PipelineState, runtime: Runtime[Ctx]) -> dict[str, object]:
        known = await load_known(pool, user_of(runtime.context))
        return {
            "investor": investor_blocks(known), "user": advisor_user_block(known),
            # The same setup state the chat reads: no sizing while a core topic is unknown.
            "unknown": missing_core(setup_of(known)), "names": desk_names(known.persona),
            "revisions": 0, "story": None,
        }  # fmt: skip

    async def analyst(state: PipelineState, runtime: Runtime[Ctx]) -> dict[str, object]:
        ticker = state["ticker"]
        redraft = state.get("story") is not None
        previous = {"story": state["story"], "review": state["review"]} if redraft else None
        revision = state["revisions"] + 1
        detail = progress.ANALYST_REDRAFTING.format(revision=revision)
        names = state["names"]
        emit.progress(
            "analyst", detail if redraft else progress.ANALYST_DRAFTING, names["analyst_name"]
        )
        prompt = render_analyst_prompt(ticker, state["investor"], previous, names)
        task = analyst_text.TASK.format(ticker=ticker)
        story = await team.analyst(prompt, task, runtime.context)
        return {"story": story, "revisions": state["revisions"] + (1 if redraft else 0)}

    async def checker(state: PipelineState, runtime: Runtime[Ctx]) -> dict[str, object]:
        ticker = state["ticker"]
        last_round = state["revisions"] >= max_revisions
        previous = state.get("review") if state["revisions"] else None
        names = state["names"]
        emit.progress("checker", progress.CHECKER_CHECKING, names["checker_name"])
        prompt = render_checker_prompt(ticker, state["story"], previous, last_round, names)
        task = checker_text.TASK.format(ticker=ticker)
        review = await team.checker(prompt, task, runtime.context)
        verdict = progress.CHECKER_VERDICT.format(verdict=review["verdict"])
        emit.progress("checker", verdict, names["checker_name"])
        return {"review": review}

    def after_checker(state: PipelineState) -> str:
        return "analyst" if needs_revision(state, max_revisions) else "advisor"

    async def advisor(state: PipelineState, runtime: Runtime[Ctx]) -> dict[str, object]:
        ticker = state["ticker"]
        emit.progress("advisor", progress.STRATEGIST_SIZING, state["names"]["strategist_name"])
        prompt = render_advisor_prompt(
            ticker,
            state["user"],
            state["investor"],
            state["unknown"],
            state["story"],
            state["review"],
            state["names"],
        )
        task = strategist_text.TASK.format(ticker=ticker)
        advice = await team.advisor(prompt, task, runtime.context)
        return {"advice": advice}

    async def save(state: PipelineState, runtime: Runtime[Ctx]) -> dict[str, object]:
        thesis_id = await theses.save(
            pool, user_of(runtime.context), state["ticker"], state["story"], state["review"],
            state["advice"], state["revisions"],
        )  # fmt: skip
        emit.progress("save", progress.SAVING, state["names"]["bot_name"])
        return {"thesis_id": thesis_id}

    graph = StateGraph(PipelineState, context_schema=Ctx)
    for name, node in [
        ("load_context", load_context),
        ("analyst", analyst),
        ("checker", checker),
        ("advisor", advisor),
        ("save", save),
    ]:
        graph.add_node(name, node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "analyst")
    graph.add_edge("analyst", "checker")
    graph.add_conditional_edges("checker", after_checker, ["analyst", "advisor"])
    graph.add_edge("advisor", "save")
    graph.add_edge("save", END)
    return graph.compile(checkpointer=False)
