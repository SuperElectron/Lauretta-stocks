"""The chat graph: reload context, a model node, a tool node, the loop between them, and a notice.

A new investor message that is exactly `approve soul <id>` or `reject soul <id>` is applied by
code in the context step, before the model runs, and the reply ends with what it did. A turn that
proposed a soul change ends with the proposal and its approval phrase. Both are written by code.
Whether the turn opens with the first-contact intro is decided in code too (`setup.opening`).

The graph is built once for everyone. Each run's user comes from its context (`Ctx`): the context
step loads that user's data, and the tools read the same context.
"""

from collections.abc import Callable

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime
from loguru import logger
from psycopg_pool import AsyncConnectionPool

from src.graph import compaction, emit, progress
from src.graph.context import investor_blocks, load_known, theses_block
from src.graph.ctx import Ctx, user_of
from src.graph.history import answered, recent
from src.graph.llm import complete, with_backoff
from src.graph.render import render_assistant_prompt
from src.graph.research import research_block
from src.graph.setup import opening, render_setup, setup_of, stage
from src.graph.state import ChatState
from src.persona.approval import (
    decide,
    decision_notice,
    parse_decision,
    proposal_notice,
    proposals_in_turn,
    soul_change_block,
)
from src.persona.layers import desk_names, render_persona
from src.runs import Runs

# The model sees the latest messages only; long-term facts live in memory, not the transcript.
HISTORY_MESSAGES = 40


def build_chat(
    pool: AsyncConnectionPool,
    checkpointer: BaseCheckpointSaver,
    tools: list[BaseTool],
    model: BaseChatModel,
    recursion_limit: int,
    runs: Runs | None = None,
    compact: Callable | None = None,
) -> CompiledStateGraph:
    """`runs`: where research the desk started is tracked (`src/runs.py`); without it the desk
    reports none. `compact`: the node that summarises a long thread (`compaction.build_compact`);
    without it the model sees the last `HISTORY_MESSAGES` and nothing older."""
    bound = with_backoff(model.bind_tools(tools))

    async def context(state: ChatState, runtime: Runtime[Ctx]) -> dict[str, object]:
        user_id = user_of(runtime.context)
        update: dict[str, object] = {}
        latest = state["messages"][-1]
        # Only on the investor's own message: after a tool step the decision is already made.
        if isinstance(latest, HumanMessage):
            phrase = parse_decision(latest.text)
            decision = await decide(pool, user_id, *phrase) if phrase else {}
            update["soul_decision"] = decision
            update["soul_change"] = soul_change_block(**decision) if decision else ""
            # Asked once per message: a finished run is reported for the whole turn, tool
            # steps included, and only then forgotten.
            update["research"], update["reported_runs"] = (
                await research_block(runs, user_id) if runs else ("", [])
            )
        known = await load_known(pool, user_id)
        setup = setup_of(known)
        return {
            **update,
            "persona": render_persona(known.persona),
            "context": f"{investor_blocks(known)}\n{await theses_block(pool, user_id)}",
            "setup": setup,
            "names": desk_names(known.persona),
            "opening": opening(setup, state["messages"]),
        }

    async def agent(state: ChatState) -> dict[str, object]:
        setup, names = state["setup"], state["names"]
        prompt = render_assistant_prompt(
            state["persona"],
            state["context"],
            render_setup(setup, names),
            stage(setup),
            state["names"],
            state["soul_change"],
            state["opening"],
            state.get("summary", ""),
            state.get("research", ""),
        )
        # Everything after the summary, which covers the messages before `summarized`.
        start = state.get("summarized", 0)
        limit = HISTORY_MESSAGES + (compaction.BATCH if compact else 0)
        history = recent(answered(state["messages"][start:]), limit)
        emit.progress("assistant", progress.ASSISTANT_WORKING, state["names"]["bot_name"])
        reply = await bound.ainvoke([SystemMessage(content=prompt), *history])
        return {"messages": [complete(reply)]}

    async def notice(state: ChatState, runtime: Runtime[Ctx]) -> dict[str, object]:
        """Appends what this turn's soul decision did, then each soul proposal made this turn, to
        the final reply (same id, so replaced), and sends each to a streaming caller as its own
        notice. The runs this turn reported are forgotten here, where the reply exists: a turn
        that died before one never reported them, and says so again next time."""
        if runs and state.get("reported_runs"):
            try:
                await runs.clear(user_of(runtime.context), state["reported_runs"])
            except Exception:
                # The reply stands; an unforgotten run is simply reported again next time.
                logger.exception("chat.research_unclearable")
        decision = state.get("soul_decision")
        notices = [decision_notice(decision)] if decision else []
        notices.extend(proposal_notice(p) for p in proposals_in_turn(state["messages"]))
        if not notices:
            return {}
        reply = state["messages"][-1]
        for text in notices:
            emit.notice(text)
        text = "\n\n".join([reply.text, *notices])
        return {"messages": [reply.model_copy(update={"content": text})]}

    graph = StateGraph(ChatState, context_schema=Ctx)
    graph.add_node("context", context)
    graph.add_node("agent", agent)
    # Not retried: a retry re-runs every call in the message, a whole research run included.
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("notice", notice)
    graph.add_edge(START, "context")
    graph.add_edge("context", "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "notice"})
    graph.add_edge("tools", "context")
    if compact is None:
        graph.add_edge("notice", END)
    else:
        graph.add_node("compact", compact)
        graph.add_edge("notice", "compact")
        graph.add_edge("compact", END)
    return graph.compile(checkpointer=checkpointer).with_config(recursion_limit=recursion_limit)
