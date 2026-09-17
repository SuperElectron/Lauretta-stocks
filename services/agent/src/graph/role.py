"""A research role: a model node, a tool node, and the loop between them until it submits."""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from src.errors import RoleDidNotSubmit
from src.graph.ctx import Ctx, user_of
from src.graph.llm import complete, with_backoff
from src.graph.state import RoleState
from src.prompts import errors
from src.prompts.tools import SUBMIT_REMINDER

# Reminders to submit before a role that keeps answering in text fails hard.
MAX_REMINDERS = 2

# Runs the role with a system prompt and a task, for the run's user (its tools read the
# context), and returns what it submitted.
Role = Callable[[str, str, Ctx], Awaitable[dict[str, Any]]]


def build_role(
    name: str, model: BaseChatModel, tools: list[BaseTool], recursion_limit: int
) -> Role:
    """Compiles the role's loop. It ends when the submit tool writes a result."""
    # One call per step, so submit never runs beside a lookup whose result it has not read.
    bound = with_backoff(model.bind_tools(tools, parallel_tool_calls=False))
    # Every role has exactly one submit tool; building a role without one is a programming error.
    (submit,) = [t.name for t in tools if t.name.startswith("submit_")]

    async def agent(state: RoleState) -> dict[str, object]:
        prompt = SystemMessage(content=state["system_prompt"])
        return {"messages": [complete(await bound.ainvoke([prompt, *state["messages"]]))]}

    def after_agent(state: RoleState) -> str:
        if state["messages"][-1].tool_calls:
            return "tools"
        return "remind" if state.get("reminders", 0) < MAX_REMINDERS else END

    def remind(state: RoleState) -> dict[str, object]:
        """A reply without a tool call hands nothing in; say so, in code, and let it try again."""
        reminder = HumanMessage(SUBMIT_REMINDER.format(submit=submit))
        return {"messages": [reminder], "reminders": state.get("reminders", 0) + 1}

    def after_tools(state: RoleState) -> str:
        return END if state.get("result") is not None else "agent"

    graph = StateGraph(RoleState, context_schema=Ctx)
    graph.add_node("agent", agent)
    graph.add_node("tools", ToolNode(tools))
    graph.add_node("remind", remind)
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", after_agent, ["tools", "remind", END])
    graph.add_edge("remind", "agent")
    graph.add_conditional_edges("tools", after_tools, ["agent", END])
    # Never checkpointed, even when run from inside the chat's tool call.
    compiled = graph.compile(checkpointer=False).with_config(
        recursion_limit=recursion_limit, run_name=name
    )

    async def run(system_prompt: str, task: str, context: Ctx) -> dict[str, Any]:
        final = await compiled.ainvoke(
            {
                "system_prompt": system_prompt,
                "messages": [HumanMessage(task)],
                "result": None,
                "reminders": 0,
            },
            context=Ctx(user_id=user_of(context)),
        )
        if final.get("result") is None:
            raise RoleDidNotSubmit(errors.ROLE_STOPPED.format(role=name))
        return final["result"]

    return run
