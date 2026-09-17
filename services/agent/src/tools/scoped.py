"""The arguments of each tool over one investor's data: its model arguments plus `runtime`.

LangGraph injects `runtime` from the run's context (`Ctx`) and leaves it out of the schema the
model sees, so the user is never an argument the model can read or set.
"""

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ConfigDict

from src.graph.ctx import Ctx
from src.tools.models import (
    ForgetArgs,
    ProposeSoulArgs,
    RecallArgs,
    RememberArgs,
    SetHoldingArgs,
    SetIdentityArgs,
    SetUserDetailsArgs,
    SkipSetupStepArgs,
    TickerArgs,
)


class Scoped(BaseModel):
    """Injected by LangGraph, never sent by the model: who the run acts for."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    runtime: ToolRuntime[Ctx]


class ScopedTickerArgs(TickerArgs, Scoped):
    pass


class ScopedRememberArgs(RememberArgs, Scoped):
    pass


class ScopedRecallArgs(RecallArgs, Scoped):
    pass


class ScopedForgetArgs(ForgetArgs, Scoped):
    pass


class ScopedSetHoldingArgs(SetHoldingArgs, Scoped):
    pass


class ScopedSetIdentityArgs(SetIdentityArgs, Scoped):
    pass


class ScopedSetUserDetailsArgs(SetUserDetailsArgs, Scoped):
    pass


class ScopedSkipSetupStepArgs(SkipSetupStepArgs, Scoped):
    pass


class ScopedProposeSoulArgs(ProposeSoulArgs, Scoped):
    pass
