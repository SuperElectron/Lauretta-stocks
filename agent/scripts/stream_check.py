"""Streaming acceptance check: queues a chat turn through the API and times its tokens.

    STREAM_CHECK_URL=http://127.0.0.1:8000 STREAM_CHECK_API_KEY=... just stream-check

Fails (exit 1) when the first token comes more than 2s after the assistant's model starts
(its `progress` event), or when the tokens arrive as one burst rather than incrementally.
`STREAM_CHECK_API_KEY` is sent as a bearer token for the gateway; leave it unset when calling
the API directly. `STREAM_CHECK_MESSAGE` and `STREAM_CHECK_THREAD` choose what is sent where.

With `--openai` it streams `POST /v1/chat/completions` as a chat app would, on a new thread
each run (a repeated request would replay the job already answered). It also fails when the
first reasoning delta takes more than 1s after the request.
"""

import json
import os
import sys
import time

import httpx

MAX_FIRST_TOKEN_SECONDS = 2.0
MAX_FIRST_REASONING_SECONDS = 1.0
# Tokens this many or more, all within this window, came as one burst, not a stream.
BURST_TOKENS = 5
BURST_SECONDS = 0.05


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
        model_start, stamps = None, []
        with http.stream("GET", job["events_url"]) as response:
            response.raise_for_status()
            for name, data in events(response):
                now = time.monotonic() - started
                if name == "token":
                    stamps.append(now)
                    continue
                print(f"{now:7.3f}s {name}: {json.dumps(data)[:160]}")
                if name == "progress" and data["stage"] == "assistant" and model_start is None:
                    model_start = now
                elif name == "reset":
                    # A retry voided the partial reply; time the attempt that follows.
                    model_start, stamps = now, []
                elif name in ("done", "error"):
                    break
    return verdict(model_start, stamps)


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
    first_reasoning, model_start, stamps = None, None, []
    with http.stream("POST", "/v1/chat/completions", json=body, headers=thread) as response:
        response.raise_for_status()
        for data in openai_chunks(response):
            now = time.monotonic() - started
            if "error" in data:
                print(f"{now:7.3f}s error: {data['error']['code']}: {data['error']['message']}")
                return 1
            delta = data["choices"][0]["delta"]
            if delta.get("content"):
                stamps.append(now)
            elif delta.get("reasoning_content"):
                print(f"{now:7.3f}s reasoning: {delta['reasoning_content'].strip()[:160]}")
                first_reasoning = now if first_reasoning is None else first_reasoning
                if model_start is None and delta["reasoning_content"].startswith("The Director"):
                    model_start = now
    if first_reasoning is None:
        print("FAIL: no reasoning delta was streamed")
        return 1
    print(f"first reasoning delta {first_reasoning:.3f}s after the request")
    late = first_reasoning > MAX_FIRST_REASONING_SECONDS
    if late:
        print(f"FAIL: first reasoning delta later than {MAX_FIRST_REASONING_SECONDS}s")
    return verdict(model_start, stamps, failed=late)


def verdict(model_start: float | None, stamps: list[float], failed: bool = False) -> int:
    if model_start is None or not stamps:
        print("FAIL: no model start or no tokens were streamed")
        return 1
    first = stamps[0] - model_start
    gaps = [b - a for a, b in zip(stamps, stamps[1:], strict=False)]
    print(f"tokens: {len(stamps)}; first token {first:.3f}s after model start")
    if gaps:
        median, largest = sorted(gaps)[len(gaps) // 2], max(gaps)
        print(f"gaps between tokens: median {median * 1000:.1f}ms, max {largest * 1000:.1f}ms")
    if first > MAX_FIRST_TOKEN_SECONDS:
        print(f"FAIL: first token later than {MAX_FIRST_TOKEN_SECONDS}s")
        failed = True
    if len(stamps) >= BURST_TOKENS and stamps[-1] - stamps[0] < BURST_SECONDS:
        print(f"FAIL: all {len(stamps)} tokens arrived within {BURST_SECONDS * 1000:.0f}ms")
        failed = True
    print("FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
