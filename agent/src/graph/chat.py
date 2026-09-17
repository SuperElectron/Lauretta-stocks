"""The chat graph: reload context, a model node, a tool node, the loop between them, and a notice.

A new investor message that is exactly `approve soul <id>` or `reject soul <id>` is applied by
code in the context step, before the model runs. A turn that proposed a soul change ends with
the proposal and its approval phrase appended to the reply, also by code.
"""

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from psycopg_pool import AsyncConnectionPool

from src.graph.context import investor_blocks, persona_blocks, theses_block
from src.graph.history import answered, recent
from src.graph.llm import complete, with_backoff
from src.graph.prompts.assistant import render_assistant_prompt
from src.graph.state import ChatState, stage
from src.persona.approval import decide, parse_decision, proposal_notice, proposals_in_turn

# The model sees the latest messages only; long-term facts live in memory, not the transcript.
HISTORY_MESSAGES = 40


def build_chat(
    pool: AsyncConnectionPool,
    user_id: str,
    checkpointer: BaseCheckpointSaver,
    tools: list[BaseTool],
    model: BaseChatModel,
    recursion_limit: int,
) -> CompiledStateGraph:
    bound = with_backoff(model.bind_tools(tools))

    async def context(state: ChatState) -> dict[str, object]:
        update: dict[str, object] = {}
        latest = state["messages"][-1]
        # Only on the investor's own message: after a tool step the decision is already made.
        if isinstance(latest, HumanMessage):
            decision = parse_decision(latest.text)
            update["soul_change"] = await decide(pool, user_id, *decision) if decision else ""
        persona, unnamed = await persona_blocks(pool, user_id)
        investor, unknown = await investor_blocks(pool, user_id)
        return {
            **update,
            "persona": persona,
            "context": f"{investor}\n{await theses_block(pool, user_id)}",
            "unknown": unknown,
            "unnamed": unnamed,
        }

    async def agent(state: ChatState) -> dict[str, object]:
        unknown, unnamed = state["unknown"], state["unnamed"]
        prompt = render_assistant_prompt(
            state["persona"],
            state["context"],
            unknown,
            unnamed,
            stage(unknown, unnamed),
            state["soul_change"],
        )
        history = recent(answered(state["messages"]), HISTORY_MESSAGES)
        reply = await bound.ainvoke([SystemMessage(content=prompt), *history])
        return {"messages": [complete(reply)]}

    def notice(state: ChatState) -> dict[str, object]:
        """Appends each soul proposal made this turn to the final reply (same id, so replaced)."""
        proposals = proposals_in_turn(state["messages"])
        if not proposals:
            return {}
        reply = state["messages"][-1]
        text = "\n\n".join([reply.text, *(proposal_notice(p) for p in proposals)])
        return {"messages": [reply.model_copy(update={"content": text})]}

    graph = StateGraph(ChatState)
    graph.add_node("context", context)
    graph.add_node("agent", agent)
    # Not retried: a retry re-runs every call in the message, a whole research run included.
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("notice", notice)
    graph.add_edge(START, "context")
    graph.add_edge("context", "agent")
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", END: "notice"})
    graph.add_edge("tools", "context")
    graph.add_edge("notice", END)
    return graph.compile(checkpointer=checkpointer).with_config(recursion_limit=recursion_limit)
