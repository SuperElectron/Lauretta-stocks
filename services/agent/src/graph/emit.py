"""What graph nodes tell a streaming caller besides tokens and state: progress, notices, retries.

Each call writes to LangGraph's custom stream (`stream_mode="custom"`); when the graph is run
with `ainvoke`, as the CLI does, nothing is written. Call these only from inside a node.
"""

from langgraph.config import get_stream_writer


def progress(stage: str, detail: str, name: str) -> None:
    """A step of `stage`, done by the agent currently called `name`."""
    get_stream_writer()({"event": "progress", "stage": stage, "detail": detail, "name": name})


def notice(text: str) -> None:
    """A code-written notice for the investor, sent apart from the model's tokens."""
    get_stream_writer()({"event": "notice", "text": text})


def retry(attempt: int) -> None:
    """The model call failed and runs again, so tokens already streamed from it are void."""
    get_stream_writer()({"event": "retry", "attempt": attempt})
