"""How a thread opens is decided in code: the intro on first contact only; with the investor's name
known, a new thread greets them by it and never asks what to call them."""

from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from src.graph import chat as chat_module
from src.graph.chat import build_chat
from src.graph.context import Known
from src.graph.ctx import Ctx
from src.graph.render import render_assistant_prompt
from src.graph.setup import compute_setup, opening, render_setup
from src.persona.layers import build_persona, desk_names, render_persona
from tests.unit.test_setup import CORE, NAME
from tests.utils import ScriptedModel, call

INTRO = ("Here's my team", "What should I call you?", "first contact")


def setup_for(rows: list[dict]) -> list[dict]:
    return compute_setup(build_persona(rows), CORE, 0)


@pytest.mark.parametrize(
    ("rows", "messages", "expected"),
    [
        ([], [HumanMessage("hi")], "intro"),
        ([NAME], [HumanMessage("hi")], "welcome"),
        ([], [HumanMessage("hi"), AIMessage("Hello."), HumanMessage("again")], ""),
        ([NAME], [HumanMessage("hi"), AIMessage("Hello."), HumanMessage("again")], ""),
        # Still the first reply while the turn loops through its tools.
        ([], [HumanMessage("hi"), call("recall", {"query": "x"}),
              ToolMessage("{}", tool_call_id="call-1")], "intro"),
    ],
)  # fmt: skip
def test_opening_follows_the_name_and_the_thread(rows, messages, expected):
    assert opening(setup_for(rows), messages) == expected


def prompt_for(rows: list[dict], how: str) -> str:
    persona = build_persona(rows)
    names = desk_names(persona)
    setup = render_setup(compute_setup(persona, CORE, 0), names)
    return render_assistant_prompt(render_persona(persona), "", setup, "setup", names, "", how)


def test_only_first_contact_gets_the_intro():
    assert all(part in prompt_for([], "intro") for part in INTRO)
    for rows, how in (([NAME], "welcome"), ([NAME], ""), ([], "")):
        prompt = prompt_for(rows, how)
        assert not [part for part in INTRO if part in prompt], how
    welcome = prompt_for([NAME], "welcome")
    assert "greet them by the name in <user>" in welcome
    assert "do not ask what to call them" in welcome


class Recording(ScriptedModel):
    """Keeps the system prompt of every call."""

    prompts: list[str] = []

    def _generate(self, messages: list[Any], *args: Any, **kwargs: Any) -> Any:
        assert isinstance(messages[0], SystemMessage)
        self.prompts.append(messages[0].content)
        return super()._generate(messages, *args, **kwargs)


@pytest.fixture
def known_name(monkeypatch):
    async def load_known(_pool, _user_id):
        return Known(persona=build_persona([NAME]), remembered=[], positions=[])

    async def theses_block(_pool, _user_id):
        return "<theses>\nnone yet\n</theses>"

    monkeypatch.setattr(chat_module, "load_known", load_known)
    monkeypatch.setattr(chat_module, "theses_block", theses_block)


@pytest.mark.usefixtures("known_name")
async def test_a_new_thread_with_the_name_known_greets_without_the_intro():
    model = Recording(messages=iter([AIMessage("Morning, Boss."), AIMessage("Sure.")]), prompts=[])
    graph = build_chat(None, InMemorySaver(), [], model, 20)
    config = {"configurable": {"thread_id": "new"}}

    first = await graph.ainvoke({"messages": [HumanMessage("hi")]}, config, context=Ctx("friend"))
    await graph.ainvoke({"messages": [HumanMessage("next")]}, config, context=Ctx("friend"))

    assert first["opening"] == "welcome"
    greet, later = model.prompts
    assert "greet them by the name in <user>" in greet
    assert not [part for part in INTRO if part in greet + later]
    assert "greet them" not in later
