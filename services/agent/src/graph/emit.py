"""What graph nodes tell a streaming caller besides tokens and state: progress, notices, retries.

Each call writes to LangGraph's custom stream (`stream_mode="custom"`); when the graph is run
with `ainvoke`, as the CLI does, or outside a graph altogether, nothing is written. These are for
nodes and the tools a node runs; nobody is listening anywhere else.
"""

from typing import Any

from langgraph.config import get_stream_writer


def _write(chunk: dict[str, Any]) -> None:
    try:
        writer = get_stream_writer()
    except (KeyError, RuntimeError):
        # No graph run around this call, so there is no stream to write to.
        return
    writer(chunk)


def progress(stage: str, detail: str, name: str) -> None:
    """A step of `stage`, done by the agent currently called `name`."""
    _write({"event": "progress", "stage": stage, "detail": detail, "name": name})


def notice(text: str) -> None:
    """A code-written notice for the investor, sent apart from the model's tokens."""
    _write({"event": "notice", "text": text})


def retry(attempt: int) -> None:
    """The model call failed and runs again, so tokens already streamed from it are void."""
    _write({"event": "retry", "attempt": attempt})
