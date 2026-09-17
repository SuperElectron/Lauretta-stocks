"""Isolation in the OpenAI-compatible routes: a chat serves only the caller's own model, and the
model list shows the caller's model (every user's only to AnythingLLM)."""

import pytest

from tests.unit.openai.conftest import body, client_for

pytestmark = pytest.mark.usefixtures("db")


async def test_chat_completions_serve_only_the_callers_own_model(broker, worker):
    async with client_for(broker) as mat:
        other = await mat.post("/v1/chat/completions", json=body("hi", model="lauretta-max"))
        plain = await mat.post("/v1/chat/completions", json=body("hi", model="lauretta"))
        own = await mat.post("/v1/chat/completions", json=body("hi"))
    assert (other.status_code, other.json()["error"]["code"]) == (404, "model_not_found")
    assert plain.status_code == 404
    assert own.status_code == 200
    assert [job.user for job in worker.jobs] == ["mat"]


async def test_models_list_the_callers_model_or_every_users_for_anythingllm(broker):
    async with client_for(broker, user="max") as max_:
        own = await max_.get("/v1/models")
    async with client_for(broker, user=None) as anythingllm:
        every = await anythingllm.get("/v1/models", headers={"X-Lauretta-Caller": "anythingllm"})
        owner_key = await anythingllm.get("/v1/models", headers={"X-Lauretta-Caller": "owner"})
    assert [m["id"] for m in own.json()["data"]] == ["lauretta-max"]
    assert [m["id"] for m in every.json()["data"]] == ["lauretta-mat", "lauretta-max"]
    assert owner_key.status_code == 401
