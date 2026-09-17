"""Who a run acts for: LangGraph runtime context, set by code for each run and never by a model.

Graphs are built once with `context_schema=Ctx` and run with `context=Ctx(user_id=...)`. Nodes
read it from `Runtime[Ctx]`; tools from `ToolRuntime[Ctx]`, which LangGraph leaves out of the
schema the model sees, so the model can neither read nor set the user.
"""

from dataclasses import dataclass

from src.errors import NoUser


@dataclass(frozen=True)
class Ctx:
    user_id: str


def user_of(context: object) -> str:
    """The run's user; `NoUser` when the run was started without a context."""
    if not isinstance(context, Ctx) or not context.user_id:
        raise NoUser
    return context.user_id
