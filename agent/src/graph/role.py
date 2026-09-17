"""A research role: a model node, a tool node, and the loop between them until it submits."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.errors import RoleDidNotSubmit
from src.graph.llm import complete, with_backoff
from src.graph.state import RoleState

# Runs the role with a system prompt and a task, and returns what it submitted.
Role = Callable[[str, str], Awaitable[dict[str, Any]]]


def build_role(
    name: str, model: BaseChatModel, tools: list[BaseTool], recursion_limit: int
) -> Role:
    """Compiles the role's loop. It ends when the submit tool writes a result."""
    # One call per step, so submit never runs beside a lookup whose result it has not read.
    bound = with_backoff(model.bind_tools(tools, parallel_tool_calls=False))

    async def agent(state: RoleState) -> dict[str, object]:
        prompt = SystemMessage(content=state["system_prompt"])
        return {"messages": [complete(await bound.ainvoke([prompt, *state["messages"]]))]}

    def after_agent(state: RoleState) -> str:
        return "tools" if state["messages"][-1].tool_calls else END

    def after_tools(state: RoleState) -> str:
        return END if state.get("result") is not None else "agent"

    graph = StateGraph(RoleState)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", after_agent, ["tools", END])
    graph.add_conditional_edges("tools", after_tools, ["agent", END])
    # Never checkpointed, even when run from inside the chat's tool call.
    compiled = graph.compile(checkpointer=False).with_config(
        recursion_limit=recursion_limit, run_name=name
    )

    async def run(system_prompt: str, task: str) -> dict[str, Any]:
        final = await compiled.ainvoke(
            {"system_prompt": system_prompt, "messages": [HumanMessage(task)], "result": None}
        )
        if final.get("result") is None:
            raise RoleDidNotSubmit(f"the {name} stopped without submitting its work")
        return final["result"]

    return run
