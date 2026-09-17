import pytest

from src.api.openai import digests, threads
from src.api.openai.models import ChatRequest
from src.queue import keys
from tests.unit.openai.conftest import body


async def test_models_lists_the_director(client):
    response = await client.get("/v1/models")
    assert [m["id"] for m in response.json()["data"]] == ["lauretta"]


@pytest.mark.parametrize(
    ("payload", "status", "code"),
    [
        (body("hello", model="gpt-4o"), 404, "model_not_found"),
        ({"model": "lauretta", "messages": []}, 400, "invalid_request"),
        (
            {"model": "lauretta", "messages": [{"role": "user", "content": 7}]},
            400,
            "invalid_request",
        ),
        (body("hello", "an answer"), 400, "invalid_last_message"),
        (body("", "an answer", "hello"), 400, "invalid_first_message"),
        (body("x" * 20_001), 400, "message_too_long"),
    ],
)
async def test_bad_requests_are_openai_errors_and_queue_nothing(
    client, broker, db, payload, status, code
):
    response = await client.post("/v1/chat/completions", json=payload)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert await broker.exists(keys.JOBS) == 0
    assert db.owners == {}


async def test_errors_never_echo_input_or_leak_internals(client, broker, monkeypatch):
    unknown = await client.post("/v1/chat/completions", json=body("hi", model="my-secret-model"))
    assert unknown.status_code == 404 and "my-secret-model" not in unknown.text
    secret = "sk-live-do-not-echo"
    bad = await client.post(
        "/v1/chat/completions",
        json={"model": "lauretta", "messages": [{"role": "user", "content": {"k": secret}}]},
    )
    assert bad.status_code == 400 and secret not in bad.text
    not_json = await client.post("/v1/chat/completions", content=b"{" + secret.encode())
    assert not_json.status_code == 400 and secret not in not_json.text

    async def database_down(*_args):
        raise RuntimeError("postgresql://lauretta:hunter2@db/lauretta refused")

    monkeypatch.setattr(threads.threads, "create", database_down)
    down = await client.post("/v1/chat/completions", json=body("hello"))
    assert down.status_code == 500
    assert "hunter2" not in down.text and "Traceback" not in down.text
    assert await broker.exists(keys.JOBS) == 0


async def test_a_thread_started_by_someone_else_is_not_found(client, broker, db):
    request = ChatRequest.model_validate(body("hello", "hi", "more"))
    db.owners[digests.first_message_thread("friend", request)] = "someone-else"

    response = await client.post("/v1/chat/completions", json=body("hello", "hi", "more"))

    assert (response.status_code, response.json()["error"]["code"]) == (404, "thread_not_found")
    assert await broker.exists(keys.JOBS) == 0


async def test_a_bad_thread_header_is_refused(client):
    response = await client.post(
        "/v1/chat/completions", json=body("hello"), headers={"X-Thread-Id": "no spaces"}
    )
    assert response.json()["error"]["code"] == "invalid_thread_id"
