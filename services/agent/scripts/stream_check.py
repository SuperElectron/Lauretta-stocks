"""Streaming acceptance check: queues a chat turn through the API and times its tokens.

    STREAM_CHECK_URL=http://127.0.0.1:8000 STREAM_CHECK_API_KEY=... just stream-check

Fails (exit 1) when the assistant model shows nothing (no `reasoning` or `token` event) for
more than 2s after it starts (its `progress` event), or when the tokens arrive as one burst
rather than incrementally. A reasoning model thinks before it answers, so the first token is
reported but not gated. `STREAM_CHECK_API_KEY` is sent as a bearer token for the gateway; leave
it unset when calling the API directly. `STREAM_CHECK_MESSAGE` and `STREAM_CHECK_THREAD` choose
what is sent where.

With `--openai` it streams `POST /v1/chat/completions` as a chat app would, on a new thread
each run, so the timings are for a fresh turn. It passes when the first reasoning delta (the
first visible activity) comes within 1s of the request and the tokens are incremental. The
first reasoning from the model itself and the first content token are reported, not gated.
"""

import json
import os
import sys
import time

import httpx
from stream_report import DESK_LINE, MODEL_START, report, verdict

from src.prompts import notes

MAX_FIRST_MODEL_OUTPUT_SECONDS = 2.0
MAX_FIRST_REASONING_SECONDS = 1.0


def events(response: httpx.Response):
    """(event, data) for each SSE frame as it arrives; comments (pings) are skipped."""
    name, data = None, []
    for line in response.iter_lines():
        if line == "":
            if name is not None:
                yield name, json.loads("\n".join(data))
            name, data = None, []
        elif line.startswith("event: "):
            name = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data.append(line.removeprefix("data: "))


def main() -> int:
    base = os.environ.get("STREAM_CHECK_URL", "http://127.0.0.1:8000").rstrip("/")
    key = os.environ.get("STREAM_CHECK_API_KEY")
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    body = {
        "kind": "chat",
        "thread_id": os.environ.get("STREAM_CHECK_THREAD", "stream-check"),
        "message": os.environ.get("STREAM_CHECK_MESSAGE", "In three sentences, what can you do?"),
    }
    with httpx.Client(base_url=base, headers=headers, timeout=httpx.Timeout(30, read=120)) as http:
        if "--openai" in sys.argv[1:]:
            return check_openai(http, body["message"])
        posted = http.post("/v1/jobs", json=body)
        posted.raise_for_status()
        job = posted.json()
        print(f"job {job['job_id']} queued")
        started = time.monotonic()
        model_start, thought, stamps = None, None, []
        with http.stream("GET", job["events_url"]) as response:
            response.raise_for_status()
            for name, data in events(response):
                now = time.monotonic() - started
                if name == "token":
                    stamps.append(now)
                    continue
                if name == "reasoning":
                    thought = now if thought is None else thought
                    continue
                print(f"{now:7.3f}s {name}: {json.dumps(data)[:160]}")
                if name == "progress" and data["stage"] == "assistant" and model_start is None:
                    model_start = now
                elif name == "reset":
                    # A retry voided the partial reply; time the attempt that follows.
                    model_start, thought, stamps = now, None, []
                elif name in ("done", "error"):
                    break
    if model_start is None:
        print("FAIL: the assistant model never started")
        return 1
    first_output = min((t for t in (thought, *stamps[:1]) if t is not None), default=None)
    late = first_output is None or first_output - model_start > MAX_FIRST_MODEL_OUTPUT_SECONDS
    if late:
        print(
            f"FAIL: the model showed nothing within {MAX_FIRST_MODEL_OUTPUT_SECONDS}s of starting"
        )
    report("first model reasoning", thought, model_start)
    return verdict(model_start, stamps, failed=late)


def openai_chunks(response: httpx.Response):
    """Each `data:` chunk as it arrives, until `[DONE]`."""
    for line in response.iter_lines():
        if line.startswith("data: "):
            if line == "data: [DONE]":
                return
            yield json.loads(line.removeprefix("data: "))


def check_openai(http: httpx.Client, message: str) -> int:
    body = {"model": "lauretta", "stream": True, "messages": [{"role": "user", "content": message}]}
    thread = {"X-Thread-Id": f"stream-check-{int(time.time())}"}
    started = time.monotonic()
    first_reasoning, model_start, thought, stamps = None, None, None, []
    with http.stream("POST", "/v1/chat/completions", json=body, headers=thread) as response:
        response.raise_for_status()
        for data in openai_chunks(response):
            now = time.monotonic() - started
            if "error" in data:
                print(f"{now:7.3f}s error: {data['error']['code']}: {data['error']['message']}")
                return 1
            delta = data["choices"][0]["delta"]
            text = delta.get("reasoning_content")
            if delta.get("content"):
                stamps.append(now)
            elif text:
                first_reasoning = now if first_reasoning is None else first_reasoning
                if not DESK_LINE.fullmatch(text) and text != notes.WAITING:
                    # The model's own reasoning: fragments, too many to print.
                    thought = now if thought is None and model_start is not None else thought
                    continue
                print(f"{now:7.3f}s reasoning: {text.strip()[:160]}")
                if model_start is None and MODEL_START.fullmatch(text.strip()):
                    model_start = now
    if first_reasoning is None:
        print("FAIL: no reasoning delta was streamed")
        return 1
    print(f"first visible activity (a reasoning delta) {first_reasoning:.3f}s after the request")
    late = first_reasoning > MAX_FIRST_REASONING_SECONDS
    if late:
        print(f"FAIL: first reasoning delta later than {MAX_FIRST_REASONING_SECONDS}s")
    report("first model reasoning", thought, model_start)
    return verdict(model_start, stamps, failed=late)


if __name__ == "__main__":
    sys.exit(main())
